import json
import os
import time
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from pydantic import ValidationError

from review_models import ReviewStatus, StructuredReviewResult


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


def _json_dump(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def resolve_api_key(explicit_api_key: str | None = None, api_key_env: str | None = None) -> str:
    if explicit_api_key and explicit_api_key.strip():
        return explicit_api_key.strip()
    if api_key_env and api_key_env.strip():
        api_key_env = api_key_env.strip()
        if api_key_env.startswith("sk-"):
            return api_key_env
        value = os.getenv(api_key_env, "").strip()
        if value:
            return value
    return os.getenv("DEEPSEEK_API_KEY", "").strip()


def build_deepseek_messages(scene_text: str, scene_metadata: dict[str, Any], canon_context: dict[str, Any]) -> list[dict[str, str]]:
    system_prompt = """你是本项目的小说审稿 Agent。

你的唯一任务是输出一个严格合法的 JSON 对象，且该 JSON 必须匹配如下结构化 review_result schema：

{
  "task_id": "string",
  "status": "lock | revise | rewrite | manual_intervention",
  "summary": "string",
  "issues": [
    {
      "id": "ISSUE-001",
      "type": "continuity | timeline | pov | knowledge | style | scene_purpose | foreshadowing | redundancy",
      "severity": "low | medium | high | critical",
      "scope": "local | scene | chapter | global",
      "target": "string",
      "message": "string",
      "suggested_action": "string"
    }
  ],
  "strengths": ["string"],
  "decision_reason": "string"
}

规则：
- 只能输出单个 JSON 对象，不要输出 markdown，不要输出解释。
- `status` 必须只在以上四个值中选择。
- `issues` 中每个 `id` 必须按 `ISSUE-001` 递增编号。
- `scope` 如果是全局，必须写 `global`。
- 如果无法可靠判断，也必须输出合法 JSON，并把 `status` 设为 `manual_intervention`。
- `decision_reason` 必须明确说明为什么给出当前结论。
- 你是 reviewer，不是 writer，不要重写正文。
"""

    user_prompt = f"""请审查下面 scene，并只返回结构化 review_result JSON。

【scene_metadata】
{_json_dump(scene_metadata)}

【canon_context】
{_json_dump(canon_context)}

【scene_text】
{scene_text}
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_manual_intervention_review_result(task_id: str, error_message: str) -> dict[str, Any]:
    message = str(error_message).strip() or "DeepSeek reviewer 返回不可用结果。"
    return StructuredReviewResult(
        task_id=task_id,
        status=ReviewStatus.manual_intervention,
        summary="DeepSeek reviewer 输出不可用，转人工介入。",
        issues=[],
        strengths=[],
        decision_reason=message,
    ).to_dict()


def parse_deepseek_review_result(task_id: str, raw_content: str) -> dict[str, Any]:
    payload = json.loads(raw_content)
    if not isinstance(payload, dict):
        raise ValueError("DeepSeek reviewer 没有返回 JSON object")

    if not str(payload.get("task_id", "")).strip():
        payload["task_id"] = task_id

    structured = StructuredReviewResult.from_dict(payload)
    return structured.to_dict()


def create_deepseek_client(api_key: str | None = None, api_key_env: str | None = None) -> OpenAI:
    resolved_api_key = resolve_api_key(api_key, api_key_env)
    if not resolved_api_key:
        raise ValueError("缺少 DEEPSEEK_API_KEY")
    return OpenAI(api_key=resolved_api_key, base_url=DEEPSEEK_BASE_URL)


def is_transient_request_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    return isinstance(error, (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError, TimeoutError, ConnectionError)) or (
        isinstance(status_code, int) and status_code >= 500
    )


def extract_message_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ValueError("DeepSeek reviewer 响应缺少 choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None) if message is not None else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("DeepSeek reviewer 响应缺少 message.content")
    return content.strip()


def review_scene_with_deepseek(
    scene_text: str,
    scene_metadata: dict,
    canon_context: dict,
) -> dict:
    task_id = str(scene_metadata.get("task_id") or canon_context.get("task_id") or "unknown-task").strip() or "unknown-task"
    timeout = float(scene_metadata.get("request_timeout") or 120)
    max_attempts = int(scene_metadata.get("max_retries") or 3)
    backoff_base = float(scene_metadata.get("retry_backoff_base") or 1.0)

    try:
        client = create_deepseek_client(
            str(scene_metadata.get("api_key") or "").strip() or None,
            str(scene_metadata.get("api_key_env") or "").strip() or None,
        )
    except Exception as error:
        return build_manual_intervention_review_result(task_id, f"DeepSeek reviewer 初始化失败：{error}")

    messages = build_deepseek_messages(scene_text, scene_metadata, canon_context)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                stream=False,
                response_format={"type": "json_object"},
                timeout=timeout,
            )
            raw_content = extract_message_content(response)
            return parse_deepseek_review_result(task_id, raw_content)
        except json.JSONDecodeError as error:
            return build_manual_intervention_review_result(task_id, f"DeepSeek reviewer JSON 解析失败：{error}")
        except ValidationError as error:
            return build_manual_intervention_review_result(task_id, f"DeepSeek reviewer schema 校验失败：{error}")
        except ValueError as error:
            return build_manual_intervention_review_result(task_id, f"DeepSeek reviewer schema 校验失败：{error}")
        except Exception as error:
            last_error = error
            if not is_transient_request_error(error) or attempt >= max_attempts:
                break
            time.sleep(backoff_base * (2 ** (attempt - 1)))

    return build_manual_intervention_review_result(task_id, f"DeepSeek reviewer 请求失败：{last_error}")


def structured_review_to_legacy_result(review_result: dict[str, Any]) -> dict[str, Any]:
    structured = StructuredReviewResult.from_dict(review_result)
    verdict = structured.status.value if structured.status is not ReviewStatus.manual_intervention else "revise"

    major_issues = [
        issue.message
        for issue in structured.issues
        if issue.severity.value in {"high", "critical"}
    ]
    minor_issues = [
        issue.message
        for issue in structured.issues
        if issue.severity.value in {"low", "medium"}
    ]

    if structured.status is ReviewStatus.manual_intervention and not major_issues:
        major_issues = [structured.decision_reason]

    legacy = {
        "task_id": structured.task_id,
        "verdict": verdict,
        "task_goal_fulfilled": structured.status is ReviewStatus.lock,
        "major_issues": major_issues,
        "minor_issues": minor_issues,
        "recommended_next_step": "lock_scene" if structured.status is ReviewStatus.lock else ("rewrite_scene" if structured.status is ReviewStatus.rewrite else "create_revision_task"),
        "summary": structured.summary,
    }
    if structured.status is ReviewStatus.manual_intervention:
        legacy["force_manual_intervention_reason"] = structured.decision_reason
    return legacy


def save_structured_deepseek_review(root: Path, review_result: dict[str, Any]) -> str:
    structured = StructuredReviewResult.from_dict(review_result)
    rel_path = f"02_working/reviews/{structured.task_id}_review_result.json"
    structured.save(root / rel_path)
    return rel_path