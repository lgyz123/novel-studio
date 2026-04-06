import json
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from pydantic import BaseModel, Field, ValidationError

from review_models import build_repair_plan_path, build_review_result_path
from revision_lineage import build_revision_lineage_path


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


class SupervisorAction(str, Enum):
    continue_revise = "continue_revise"
    continue_rewrite = "continue_rewrite"
    manual_intervention = "manual_intervention"


class SupervisorDecision(BaseModel):
    task_id: str = Field(min_length=1)
    action: SupervisorAction
    reason: str = Field(min_length=1)
    focus_points: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SupervisorDecision":
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls.parse_obj(data)


def build_supervisor_decision_path(task_id: str) -> str:
    return f"02_working/reviews/{task_id}_supervisor_decision.json"


def resolve_api_key(explicit_api_key: str | None = None, api_key_env: str | None = None) -> str:
    if explicit_api_key and explicit_api_key.strip():
        return explicit_api_key.strip()
    if api_key_env and api_key_env.strip():
        value = os.getenv(api_key_env.strip(), "").strip()
        if value:
            return value
    return os.getenv("DEEPSEEK_API_KEY", "").strip()


def create_deepseek_client(api_key: str | None = None, api_key_env: str | None = None) -> OpenAI:
    resolved_api_key = resolve_api_key(api_key, api_key_env)
    if not resolved_api_key:
        raise ValueError("缺少 DEEPSEEK_API_KEY")
    return OpenAI(api_key=resolved_api_key, base_url=DEEPSEEK_BASE_URL)


def is_supervisor_enabled(config: dict[str, Any]) -> bool:
    supervisor = config.get("supervisor", {})
    return bool(supervisor.get("enabled"))


def is_transient_request_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    return isinstance(error, (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError, TimeoutError, ConnectionError)) or (
        isinstance(status_code, int) and status_code >= 500
    )


def safe_load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def build_supervisor_context(root: Path, task_id: str, draft_file: str, max_revisions: int, trigger_reason: str) -> dict[str, Any]:
    return {
        "draft_file": draft_file,
        "max_auto_revisions": max_revisions,
        "trigger_reason": trigger_reason,
        "review_result": safe_load_json(root / build_review_result_path(task_id)),
        "repair_plan": safe_load_json(root / build_repair_plan_path(task_id)),
        "revision_lineage": safe_load_json(root / build_revision_lineage_path(task_id)),
        "lock_gate_report": safe_load_json(root / f"03_locked/reports/{task_id}_lock_gate_report.json"),
    }


def build_supervisor_messages(task_text: str, reviewer_result: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    system_prompt = """你是小说自动流水线的 supervisor。

writer 和 reviewer 仍然使用本地模型；你的职责只是替代原本需要人类拍板的升级决策。

你绝不能决定 lock。lock 仍然完全由本地 deterministic 规则处理。

你只允许输出一个 JSON 对象，字段必须严格为：
{
  "task_id": "string",
  "action": "continue_revise | continue_rewrite | manual_intervention",
  "reason": "string",
  "focus_points": ["string"]
}

判定规则：
- `continue_revise`：当前草稿方向仍可救，继续一轮定向修订有价值。
- `continue_rewrite`：当前草稿方向已偏，应该自动转重写，而不是再小修。
- `manual_intervention`：信息不足、风险过高、或继续自动化大概率空转。
- 如果不确定，必须选择 `manual_intervention`。
- 不要输出 markdown，不要输出解释文字，不要输出额外字段。
"""

    user_prompt = json.dumps(
        {
            "task_text": task_text,
            "reviewer_result": reviewer_result,
            "supervision_context": context,
        },
        ensure_ascii=False,
        indent=2,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def extract_message_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ValueError("DeepSeek supervisor 响应缺少 choices")
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None) if message is not None else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("DeepSeek supervisor 响应缺少 message.content")
    return content.strip()


def build_fallback_supervisor_decision(task_id: str, reason: str) -> dict[str, Any]:
    return SupervisorDecision(
        task_id=task_id,
        action=SupervisorAction.manual_intervention,
        reason=reason.strip() or "DeepSeek supervisor 未能给出可用决策。",
        focus_points=[],
    ).to_dict()


def run_supervisor_decision(
    root: Path,
    config: dict[str, Any],
    task_text: str,
    reviewer_result: dict[str, Any],
    draft_file: str,
    max_revisions: int,
    trigger_reason: str,
) -> dict[str, Any]:
    task_id = str(reviewer_result.get("task_id") or "unknown-task").strip() or "unknown-task"
    supervisor = config.get("supervisor", {})
    timeout = float(supervisor.get("request_timeout") or 120)
    max_attempts = int(supervisor.get("max_retries") or 3)
    backoff_base = float(supervisor.get("retry_backoff_base") or 1.0)

    try:
        client = create_deepseek_client(
            str(supervisor.get("api_key") or "").strip() or None,
            str(supervisor.get("api_key_env") or "").strip() or None,
        )
    except Exception as error:
        return build_fallback_supervisor_decision(task_id, f"DeepSeek supervisor 初始化失败：{error}")

    context = build_supervisor_context(root, task_id, draft_file, max_revisions, trigger_reason)
    messages = build_supervisor_messages(task_text, reviewer_result, context)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=str(supervisor.get("model") or DEEPSEEK_MODEL),
                messages=messages,
                stream=False,
                response_format={"type": "json_object"},
                timeout=timeout,
            )
            content = extract_message_content(response)
            decision = SupervisorDecision.from_dict(json.loads(content))
            return decision.to_dict()
        except (json.JSONDecodeError, ValidationError, ValueError) as error:
            return build_fallback_supervisor_decision(task_id, f"DeepSeek supervisor 结果解析/校验失败：{error}")
        except Exception as error:
            last_error = error
            if not is_transient_request_error(error) or attempt >= max_attempts:
                break
            time.sleep(backoff_base * (2 ** (attempt - 1)))

    return build_fallback_supervisor_decision(task_id, f"DeepSeek supervisor 请求失败：{last_error}")


def save_supervisor_decision(root: Path, decision: dict[str, Any]) -> str:
    validated = SupervisorDecision.from_dict(decision)
    rel_path = build_supervisor_decision_path(validated.task_id)
    validated.save(root / rel_path)
    return rel_path


def apply_supervisor_decision_to_reviewer_result(reviewer_result: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    validated = SupervisorDecision.from_dict(decision)
    if validated.action == SupervisorAction.manual_intervention:
        updated = dict(reviewer_result)
        updated["force_manual_intervention_reason"] = validated.reason
        return updated

    updated = dict(reviewer_result)
    updated["verdict"] = "rewrite" if validated.action == SupervisorAction.continue_rewrite else "revise"
    updated["task_goal_fulfilled"] = False
    updated["recommended_next_step"] = "rewrite_scene" if updated["verdict"] == "rewrite" else "create_revision_task"
    updated["summary"] = validated.reason

    major_issues = [str(item).strip() for item in updated.get("major_issues", []) if str(item).strip()]
    for focus_point in reversed(validated.focus_points):
        if focus_point not in major_issues:
            major_issues.insert(0, focus_point)
    if validated.reason not in major_issues:
        major_issues.insert(0, validated.reason)
    updated["major_issues"] = major_issues
    return updated