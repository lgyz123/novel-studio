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


class SupervisorTaskSpec(BaseModel):
    goal: str = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    preferred_length: str = ""
    repair_mode: str = ""


class NextSceneTaskDraft(BaseModel):
    task_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    preferred_length: str = ""

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


class SupervisorDecision(BaseModel):
    task_id: str = Field(min_length=1)
    action: SupervisorAction
    reason: str = Field(min_length=1)
    focus_points: list[str] = Field(default_factory=list)
    next_task: SupervisorTaskSpec | None = None

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


def build_next_scene_plan_path(task_id: str) -> str:
    return f"02_working/reviews/{task_id}_next_scene_task_plan.json"


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
    "focus_points": ["string"],
    "next_task": {
        "goal": "string",
        "constraints": ["string"],
        "preferred_length": "string",
        "repair_mode": "string"
    }
}

判定规则：
- `continue_revise`：当前草稿方向仍可救，继续一轮定向修订有价值。
- `continue_rewrite`：当前草稿方向已偏，应该自动转重写，而不是再小修。
- `manual_intervention`：信息不足、风险过高、或继续自动化大概率空转。
- 如果不确定，必须选择 `manual_intervention`。
- 如果 action 是 `continue_revise` 或 `continue_rewrite`，必须提供 `next_task`。
- `next_task.goal` 要能直接放进任务文件。
- `next_task.constraints` 要写成约束短句列表，不要输出 markdown 标题。
- `next_task.preferred_length` 可以为空字符串；没有必要修改时可沿用原值。
- `next_task.repair_mode` 只在 revise 时使用，可选 `local_fix | partial_redraft | full_redraft`。
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
        next_task=None,
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


def extract_markdown_field(task_text: str, field_name: str) -> str | None:
    import re

    pattern = rf"(?ms)^#\s*{re.escape(field_name)}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, task_text)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


def build_followup_task_id(task_id: str, mode: str) -> str:
    import re

    base = re.sub(r"-(?:R\d+|RW\d+)$", "", task_id)
    revise_match = re.search(r"-R(\d+)$", task_id)
    rewrite_match = re.search(r"-RW(\d+)$", task_id)
    if mode == "revise":
        next_number = int(revise_match.group(1)) + 1 if revise_match else 1
        return f"{base}-R{next_number}"
    next_number = int(rewrite_match.group(1)) + 1 if rewrite_match else 1
    return f"{base}-RW{next_number}"


def build_followup_output_target(draft_file: str, mode: str) -> str:
    import re

    path = Path(draft_file)
    stem = path.stem

    if mode == "rewrite":
        rewrite_match = re.search(r"^(.*?)(_rewrite(?:\d+)?)$", stem)
        if rewrite_match:
            base_stem = rewrite_match.group(1)
            suffix = rewrite_match.group(2)
            number_match = re.search(r"_rewrite(\d+)$", suffix)
            if number_match:
                stem = f"{base_stem}_rewrite{int(number_match.group(1)) + 1}"
            else:
                stem = f"{base_stem}_rewrite2"
        else:
            stem = f"{stem}_rewrite"
    else:
        version_matches = re.findall(r"_v(\d+)", stem)
        if version_matches:
            base_stem = re.sub(r"(?:_v\d+)+$", "", stem)
            stem = f"{base_stem}_v{int(version_matches[-1]) + 1}"
        else:
            stem = f"{stem}_v2"

    return path.with_name(f"{stem}{path.suffix}").as_posix()


def build_task_content_from_supervisor_decision(
    decision: dict[str, Any],
    task_text: str,
    draft_file: str,
    repair_plan_path: str | None = None,
) -> str | None:
    validated = SupervisorDecision.from_dict(decision)
    if validated.action == SupervisorAction.manual_intervention or validated.next_task is None:
        return None

    mode = "revise" if validated.action == SupervisorAction.continue_revise else "rewrite"
    chapter_state = extract_markdown_field(task_text, "chapter_state")
    preferred_length = validated.next_task.preferred_length.strip() or (extract_markdown_field(task_text, "preferred_length") or "").strip()
    new_task_id = build_followup_task_id(validated.task_id, mode)
    new_output_target = build_followup_output_target(draft_file, mode)
    constraint_lines = [str(item).strip() for item in validated.next_task.constraints if str(item).strip()]

    sections = [
        f"# task_id\n{new_task_id}",
        f"# goal\n{validated.next_task.goal.strip()}",
        f"# based_on\n{draft_file}",
    ]

    if chapter_state:
        sections.append(f"# chapter_state\n{chapter_state}")

    if mode == "revise" and validated.next_task.repair_mode.strip():
        sections.append(f"# repair_mode\n{validated.next_task.repair_mode.strip()}")

    if mode == "revise" and repair_plan_path:
        sections.append(f"# repair_plan\n{repair_plan_path}")

    constraints_block = "\n".join(f"- {item}" for item in constraint_lines).strip()
    sections.append(f"# constraints\n{constraints_block}")

    if preferred_length:
        sections.append(f"# preferred_length\n{preferred_length}")

    sections.append(f"# output_target\n{new_output_target}")
    return "\n\n".join(sections) + "\n"


def build_next_scene_messages(task_text: str, locked_file: str, reviewer_result: dict[str, Any], context: dict[str, Any]) -> list[dict[str, str]]:
    system_prompt = """你是小说自动流水线的 supervisor。

当前 scene 已通过本地 deterministic lock gate 并成功锁定。你的任务不是重审这一场，而是为“下一场 scene”产出任务文件草案。

你只允许输出一个 JSON 对象，字段必须严格为：
{
  "task_id": "string",
  "goal": "string",
  "constraints": ["string"],
  "preferred_length": "string"
}

规则：
- 这是“下一场”的任务，不是对当前场的复述。
- 必须承接刚锁定的 scene，但不能重复当前场已经完成的推进方式。
- `goal` 必须直接可放进 task 文件。
- `constraints` 必须是约束短句列表。
- `preferred_length` 可为空，但若能判断请给出合适范围。
- 不要输出 markdown，不要输出额外字段。
"""

    user_prompt = json.dumps(
        {
            "current_task_text": task_text,
            "locked_file": locked_file,
            "reviewer_result": reviewer_result,
            "planning_context": context,
        },
        ensure_ascii=False,
        indent=2,
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_next_scene_context(root: Path, task_id: str, locked_file: str) -> dict[str, Any]:
    notes_file = root / f"03_locked/canon/{Path(locked_file).stem}_notes.md"
    story_state_file = root / "03_locked/state/story_state.json"
    context: dict[str, Any] = {
        "locked_file": locked_file,
        "locked_scene_text": (root / locked_file).read_text(encoding="utf-8") if (root / locked_file).exists() else "",
        "locked_notes": notes_file.read_text(encoding="utf-8") if notes_file.exists() else "",
        "story_state": safe_load_json(story_state_file),
        "review_result": safe_load_json(root / build_review_result_path(task_id)),
    }
    return context


def build_next_scene_task_defaults(task_text: str, locked_file: str) -> tuple[str, str]:
    import re

    current_task_id = extract_markdown_field(task_text, "task_id") or "auto-task"
    locked_stem = Path(locked_file).stem
    scene_match = re.search(r"(ch\d+)_scene(\d+)$", locked_stem)
    if not scene_match:
        raise ValueError(f"无法从 locked 文件推断下一 scene：{locked_file}")
    chapter_label = scene_match.group(1)
    next_scene_number = int(scene_match.group(2)) + 1
    date_match = re.match(r"(\d{4}-\d{2}-\d{2})-(\d{3})", current_task_id)
    if date_match:
        next_task_id = f"{date_match.group(1)}-{int(date_match.group(2)) + 1:03d}_{chapter_label}_scene{next_scene_number:02d}_auto"
    else:
        next_task_id = f"auto_{chapter_label}_scene{next_scene_number:02d}_auto"
    output_target = f"02_working/drafts/{chapter_label}_scene{next_scene_number:02d}.md"
    return next_task_id, output_target


def run_supervisor_next_scene_task(
    root: Path,
    config: dict[str, Any],
    task_text: str,
    locked_file: str,
    reviewer_result: dict[str, Any],
) -> dict[str, Any] | None:
    supervisor = config.get("supervisor", {})
    current_task_id = str(reviewer_result.get("task_id") or extract_markdown_field(task_text, "task_id") or "unknown-task").strip() or "unknown-task"
    timeout = float(supervisor.get("request_timeout") or 120)
    max_attempts = int(supervisor.get("max_retries") or 3)
    backoff_base = float(supervisor.get("retry_backoff_base") or 1.0)

    try:
        suggested_task_id, _ = build_next_scene_task_defaults(task_text, locked_file)
        client = create_deepseek_client(
            str(supervisor.get("api_key") or "").strip() or None,
            str(supervisor.get("api_key_env") or "").strip() or None,
        )
    except Exception:
        return None

    context = build_next_scene_context(root, current_task_id, locked_file)
    context["suggested_task_id"] = suggested_task_id
    messages = build_next_scene_messages(task_text, locked_file, reviewer_result, context)
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
            payload = json.loads(content)
            if not str(payload.get("task_id", "")).strip():
                payload["task_id"] = suggested_task_id
            plan = NextSceneTaskDraft.from_dict(payload) if hasattr(NextSceneTaskDraft, "from_dict") else None
            if plan is None:
                if hasattr(NextSceneTaskDraft, "model_validate"):
                    plan = NextSceneTaskDraft.model_validate(payload)
                else:
                    plan = NextSceneTaskDraft.parse_obj(payload)
            return plan.to_dict()
        except Exception as error:
            last_error = error
            if not is_transient_request_error(error) or attempt >= max_attempts:
                break
            time.sleep(backoff_base * (2 ** (attempt - 1)))

    return None


def save_next_scene_task_plan(root: Path, plan: dict[str, Any]) -> str:
    validated = NextSceneTaskDraft.model_validate(plan) if hasattr(NextSceneTaskDraft, "model_validate") else NextSceneTaskDraft.parse_obj(plan)
    rel_path = build_next_scene_plan_path(validated.task_id)
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(validated.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return rel_path


def build_next_scene_task_content(plan: dict[str, Any], task_text: str, locked_file: str) -> str:
    validated = NextSceneTaskDraft.model_validate(plan) if hasattr(NextSceneTaskDraft, "model_validate") else NextSceneTaskDraft.parse_obj(plan)
    _, output_target = build_next_scene_task_defaults(task_text, locked_file)
    chapter_state = extract_markdown_field(task_text, "chapter_state")
    constraints_block = "\n".join(f"- {item.strip()}" for item in validated.constraints if str(item).strip())
    sections = [
        f"# task_id\n{validated.task_id}",
        f"# goal\n{validated.goal.strip()}",
        f"# based_on\n{locked_file}",
    ]
    if chapter_state:
        sections.append(f"# chapter_state\n{chapter_state}")
    sections.append(f"# constraints\n{constraints_block}")
    if validated.preferred_length.strip():
        sections.append(f"# preferred_length\n{validated.preferred_length.strip()}")
    sections.append(f"# output_target\n{output_target}")
    return "\n\n".join(sections) + "\n"


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