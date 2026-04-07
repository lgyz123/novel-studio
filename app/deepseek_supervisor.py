import json
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from pydantic import BaseModel, Field, ValidationError, model_validator

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
    scene_purpose: str = ""
    required_information_gain: list[str] = Field(default_factory=list)
    required_plot_progress: str = ""
    required_decision_shift: str = ""
    avoid_motifs: list[str] = Field(default_factory=list)
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

    @model_validator(mode="before")
    @classmethod
    def normalize_empty_next_task_for_manual_intervention(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        action = data.get("action")
        next_task = data.get("next_task")
        if action != SupervisorAction.manual_intervention and action != SupervisorAction.manual_intervention.value:
            return data
        if next_task is None:
            return data
        if isinstance(next_task, dict):
            meaningful_values = [
                value for value in next_task.values() if value not in (None, "", [], {}, ())
            ]
            if not meaningful_values:
                normalized = dict(data)
                normalized["next_task"] = None
                return normalized
        return data

    @model_validator(mode="after")
    def validate_next_task_requirement(self) -> "SupervisorDecision":
        if self.action == SupervisorAction.manual_intervention:
            return self
        if self.next_task is None:
            raise ValueError("next_task is required when action is continue_revise or continue_rewrite")
        return self

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


def build_supervisor_rescue_record_path(task_id: str) -> str:
    return f"02_working/reviews/{task_id}_supervisor_rescue.json"


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


def build_supervisor_context(
    root: Path,
    task_id: str,
    draft_file: str,
    max_revisions: int,
    trigger_reason: str,
    supervisor_round: int = 0,
    max_supervisor_rounds: int = 0,
) -> dict[str, Any]:
    return {
        "draft_file": draft_file,
        "max_auto_revisions": max_revisions,
        "trigger_reason": trigger_reason,
        "supervisor_round": supervisor_round,
        "max_supervisor_rounds": max_supervisor_rounds,
        "remaining_supervisor_rounds": max(max_supervisor_rounds - supervisor_round, 0),
        "review_result": safe_load_json(root / build_review_result_path(task_id)),
        "repair_plan": safe_load_json(root / build_repair_plan_path(task_id)),
        "revision_lineage": safe_load_json(root / build_revision_lineage_path(task_id)),
        "lock_gate_report": safe_load_json(root / f"03_locked/reports/{task_id}_lock_gate_report.json"),
    }


def build_scene10_supervisor_guardrails(task_text: str) -> str:
    lowered = task_text.lower()
    is_scene10_like = any(marker in lowered for marker in ["scene10", "scene 10", "ch01_scene10"])
    if not is_scene10_like:
        return ""

    return """

scene10 专项要求：
- 不要再让 next_task 回到“改结法 / 多打一个结 / 留下线头 / 让红绳尾端继续露出 / 让平安符或红绳本身成为最终停留结果”这些旧模式。
- 如果当前 reviewer 仍然围绕绳结、线头、红绳、平安符打转，应把它们降级为触发物，而不是最终动作结果。
- next_task 必须明确要求一种新的、轻微但不同的现实动作偏移，例如：顺手收起、没有立刻擦掉、额外确认、轻微避开、重新摆正、暂缓收尾动作。
- 重点是让“阿绣”的影响落实到码头/求活日常中的具体做活动作偏移，而不是再次留下某截东西。
"""


def build_scene10_rescue_strategy(task_text: str) -> dict[str, Any] | None:
    lowered = task_text.lower()
    is_scene10_like = any(marker in lowered for marker in ["scene10", "scene 10", "ch01_scene10"])
    if not is_scene10_like:
        return None

    return {
        "forbidden_old_patterns": [
            "改结法",
            "多打一个结",
            "再次留下线头",
            "让红绳尾端继续露出",
            "不割绳尾/不剪绳尾",
            "让平安符或红绳本身成为最终停留结果",
        ],
        "allowed_micro_shift_examples": [
            "顺手收起某物，但没有立刻处理掉",
            "本来会立刻擦掉，却多停了一息",
            "多做一次额外确认后才继续做活",
            "对一个本可直接碰触的部位轻微避开",
            "把某样物什重新摆正后才离开",
            "暂缓一个本可立即完成的收尾动作",
        ],
        "core_requirement": "必须写成一次新的、轻微但不同的现实动作偏移，不能再回到绳结、线头、红绳尾端或不割绳尾这些旧模式。",
    }


def build_supervisor_messages(task_text: str, reviewer_result: dict[str, Any], context: dict[str, Any], force_continue_preference: bool = False) -> list[dict[str, str]]:
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
- 只要你还能给出明确、可执行、低风险的下一步任务，就优先选择 `continue_revise` 或 `continue_rewrite`。
- 只有在你无法提出可执行 `next_task`、上下文明显互相冲突、或 supervisor 多轮接管后仍看不到收敛可能时，才选择 `manual_intervention`。
- 只有当 action 是 `continue_revise` 或 `continue_rewrite` 时，才必须提供 `next_task`。
- 当 action 是 `manual_intervention` 时，`next_task` 必须留空或省略。
- `next_task.goal` 要能直接放进任务文件。
- `next_task.constraints` 要写成约束短句列表，不要输出 markdown 标题。
- `next_task.preferred_length` 可以为空字符串；没有必要修改时可沿用原值。
- `next_task.repair_mode` 只在 revise 时使用，可选 `local_fix | partial_redraft | full_redraft`。
- 不要输出 markdown，不要输出解释文字，不要输出额外字段。
"""
    system_prompt += build_scene10_supervisor_guardrails(task_text)

    if force_continue_preference:
        system_prompt += """

补充要求：
- 这是 recovery 决策轮；系统明确希望继续自动化。
- 只要还能提出一个可执行的 `next_task`，就不要选择 `manual_intervention`。
- 优先给出最保守、最收敛的 continue 方案；宁可缩小目标，也不要空转式复述问题。
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


def build_supervisor_rescue_messages(
    next_task_text: str,
    source_draft_text: str,
    reviewer_result: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, str]]:
    system_prompt = """你是小说自动流水线的 supervisor-rescue writer。

本地 writer 多轮未能稳定收敛；你现在要直接写出一版“更容易通过 reviewer”的救场稿。

要求：
- 只输出小说正文 prose，不要输出标题、JSON、解释、说明或 markdown 标题。
- 必须严格服从 `next_task_text` 中的 goal、constraints、preferred_length。
- 可以重写，但不要引入任务单未允许的人物、设定、调查动作或主线外扩。
- 优先解决 reviewer 已指出的 blocking issues，让场景功能闭环。
- 如果源稿有可用段落，可以保留其方向；如果源稿方向明显偏了，可以重写，但仍要保持当前 scene 的位置与边界。
- 宁可把目标收窄，也不要写成空泛总结或解释稿。
- 输出必须是一份可直接保存为草稿文件的正文。
- 严禁输出任何元话语污染：例如 `修订说明`、`执行说明`、`推进说明`、`说明`、`注`、`备注`、`以下正文`、`正文如下`、编号总结、项目符号总结。
- 一旦正文写完就立刻停止，不要补充你为什么这样写，也不要附带“本次修改点”。
"""
    system_prompt += build_scene10_supervisor_guardrails(next_task_text)

    user_prompt = json.dumps(
        {
            "next_task_text": next_task_text,
            "source_draft_text": source_draft_text,
            "reviewer_result": reviewer_result,
            "rescue_context": context,
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
    supervisor_round: int = 0,
    max_supervisor_rounds: int = 0,
    force_continue_preference: bool = False,
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

    context = build_supervisor_context(
        root,
        task_id,
        draft_file,
        max_revisions,
        trigger_reason,
        supervisor_round=supervisor_round,
        max_supervisor_rounds=max_supervisor_rounds,
    )
    messages = build_supervisor_messages(task_text, reviewer_result, context, force_continue_preference=force_continue_preference)
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
    current_supervisor_round = int(extract_markdown_field(task_text, "supervisor_round") or "0")
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

    sections.append(f"# supervisor_round\n{current_supervisor_round + 1}")

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
    "scene_purpose": "string",
    "required_information_gain": ["string"],
    "required_plot_progress": "string",
    "required_decision_shift": "string",
    "avoid_motifs": ["string"],
  "constraints": ["string"],
  "preferred_length": "string"
}

规则：
- 这是“下一场”的任务，不是对当前场的复述。
- 必须承接刚锁定的 scene，但不能重复当前场已经完成的推进方式。
- `scene_purpose` 必须说明这一场结束时局面要发生什么新的可验证变化。
- `required_information_gain` 必须列出至少一个新的信息增量，不能只是重复上一场已经确认的事实。
- `required_plot_progress` 必须说明这一场怎样推进局面，不能只写气氛延长、余波延长或情绪回响。
- `required_decision_shift` 必须要求主角做出新的现实动作、选择或行为偏移。
- `avoid_motifs` 必须列出本场应避免原样复用的母题/触发物；如果某个母题必须复现，也只能在赋予新功能时复现。
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


def normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def build_next_scene_structural_defaults(
    task_text: str,
    locked_file: str,
    reviewer_result: dict[str, Any],
) -> dict[str, Any]:
    locked_stem = Path(locked_file).stem
    repeated_motifs = normalize_string_list(
        reviewer_result.get("motif_redundancy", {}).get("repeated_motifs", [])
    )
    goal_text = (extract_markdown_field(task_text, "goal") or "").strip()

    scene_purpose = f"承接 {locked_stem} 的结果，但必须让局面产生新的可验证变化，不能只重复上一场的余波或同一种推进动作。"
    if goal_text:
        scene_purpose = f"承接上一场结果，并围绕“{goal_text}”继续推进；场景结束时必须出现新的可验证变化，而不是只延长气氛。"

    information_gain = ["补充至少一个新的具体信息，优先落在人物关系、物件状态、风险变化或行动条件上。"]
    plot_progress = "场景结尾前必须形成可验证的推进结果，例如关系变化、行动启动、阻碍升级或新约束落地。"
    decision_shift = "主角必须做出新的现实选择或动作偏移，并让这个选择改变他接下来怎样处理眼前局面。"
    if repeated_motifs:
        avoid_motifs = repeated_motifs
    else:
        avoid_motifs = ["不要原样复用上一场已经完成功能的意象、动作或触发物"]

    return {
        "scene_purpose": scene_purpose,
        "required_information_gain": information_gain,
        "required_plot_progress": plot_progress,
        "required_decision_shift": decision_shift,
        "avoid_motifs": avoid_motifs,
    }


def enrich_next_scene_plan_payload(
    payload: dict[str, Any],
    task_text: str,
    locked_file: str,
    reviewer_result: dict[str, Any],
) -> dict[str, Any]:
    normalized = dict(payload)
    defaults = build_next_scene_structural_defaults(task_text, locked_file, reviewer_result)

    for key in ("scene_purpose", "required_plot_progress", "required_decision_shift"):
        if not str(normalized.get(key, "")).strip():
            normalized[key] = defaults[key]

    information_gain = normalize_string_list(normalized.get("required_information_gain", []))
    normalized["required_information_gain"] = information_gain or defaults["required_information_gain"]

    avoid_motifs = normalize_string_list(normalized.get("avoid_motifs", []))
    normalized["avoid_motifs"] = avoid_motifs or defaults["avoid_motifs"]

    constraints = normalize_string_list(normalized.get("constraints", []))
    structural_constraints = [
        "本场必须产生新的信息增量，不能只重复上一场余波。",
        "本场必须出现主角新的现实动作或决策偏移。",
        "若复用上一场母题，必须赋予新的功能；否则改用不同触发物。",
    ]
    for item in structural_constraints:
        if item not in constraints:
            constraints.append(item)
    normalized["constraints"] = constraints
    return normalized


def build_supervisor_rescue_context(root: Path, task_id: str, source_draft_file: str, next_task_text: str) -> dict[str, Any]:
    chapter_state_path = extract_markdown_field(next_task_text, "chapter_state")
    based_on_path = extract_markdown_field(next_task_text, "based_on")
    current_context_path = root / "02_working/context/current_context.md"
    context: dict[str, Any] = {
        "source_draft_file": source_draft_file,
        "source_draft_text": (root / source_draft_file).read_text(encoding="utf-8") if (root / source_draft_file).exists() else "",
        "chapter_state_text": (root / chapter_state_path).read_text(encoding="utf-8") if chapter_state_path and (root / chapter_state_path).exists() else "",
        "based_on_text": (root / based_on_path).read_text(encoding="utf-8") if based_on_path and (root / based_on_path).exists() else "",
        "current_context_text": current_context_path.read_text(encoding="utf-8") if current_context_path.exists() else "",
        "review_result": safe_load_json(root / build_review_result_path(task_id)),
        "repair_plan": safe_load_json(root / build_repair_plan_path(task_id)),
        "revision_lineage": safe_load_json(root / build_revision_lineage_path(task_id)),
    }
    strategy = build_scene10_rescue_strategy(next_task_text)
    if strategy is not None:
        context["scene10_rescue_strategy"] = strategy
    return context


def build_next_scene_task_defaults(task_text: str, locked_file: str) -> tuple[str, str]:
    import re

    current_task_id = extract_markdown_field(task_text, "task_id") or "auto-task"
    locked_stem = Path(locked_file).stem
    stem_match = re.search(r"(ch\d+_scene\d+)", locked_stem)
    if stem_match:
        locked_stem = stem_match.group(1)
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
            payload = enrich_next_scene_plan_payload(payload, task_text, locked_file, reviewer_result)
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


def run_supervisor_rescue_draft(
    root: Path,
    config: dict[str, Any],
    next_task_text: str,
    source_draft_file: str,
    reviewer_result: dict[str, Any],
) -> dict[str, Any] | None:
    supervisor = config.get("supervisor", {})
    task_id = str(extract_markdown_field(next_task_text, "task_id") or reviewer_result.get("task_id") or "unknown-task").strip() or "unknown-task"
    timeout = float(supervisor.get("request_timeout") or 120)
    max_attempts = int(supervisor.get("max_retries") or 3)
    backoff_base = float(supervisor.get("retry_backoff_base") or 1.0)

    try:
        client = create_deepseek_client(
            str(supervisor.get("api_key") or "").strip() or None,
            str(supervisor.get("api_key_env") or "").strip() or None,
        )
    except Exception:
        return None

    context = build_supervisor_rescue_context(root, task_id, source_draft_file, next_task_text)
    messages = build_supervisor_rescue_messages(
        next_task_text,
        str(context.get("source_draft_text") or ""),
        reviewer_result,
        context,
    )
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.chat.completions.create(
                model=str(supervisor.get("model") or DEEPSEEK_MODEL),
                messages=messages,
                stream=False,
                timeout=timeout,
            )
            content = extract_message_content(response)
            if not content.strip():
                raise ValueError("DeepSeek supervisor rescue draft 响应为空")
            return {
                "task_id": task_id,
                "source_draft_file": source_draft_file,
                "draft_text": content.strip(),
            }
        except Exception as error:
            last_error = error
            if not is_transient_request_error(error) or attempt >= max_attempts:
                break
            time.sleep(backoff_base * (2 ** (attempt - 1)))

    return {
        "task_id": task_id,
        "source_draft_file": source_draft_file,
        "error": str(last_error) if last_error is not None else "unknown-error",
    }


def save_supervisor_rescue_record(root: Path, record: dict[str, Any]) -> str:
    task_id = str(record.get("task_id") or "unknown-task").strip() or "unknown-task"
    rel_path = build_supervisor_rescue_record_path(task_id)
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return rel_path


def build_next_scene_task_content(plan: dict[str, Any], task_text: str, locked_file: str) -> str:
    enriched_plan = enrich_next_scene_plan_payload(plan, task_text, locked_file, {})
    validated = NextSceneTaskDraft.model_validate(enriched_plan) if hasattr(NextSceneTaskDraft, "model_validate") else NextSceneTaskDraft.parse_obj(enriched_plan)
    _, output_target = build_next_scene_task_defaults(task_text, locked_file)
    chapter_state = extract_markdown_field(task_text, "chapter_state")
    constraints_block = "\n".join(f"- {item.strip()}" for item in validated.constraints if str(item).strip())
    information_gain_block = "\n".join(
        f"- {item.strip()}" for item in validated.required_information_gain if str(item).strip()
    )
    avoid_motifs_block = "\n".join(f"- {item.strip()}" for item in validated.avoid_motifs if str(item).strip())
    sections = [
        f"# task_id\n{validated.task_id}",
        f"# goal\n{validated.goal.strip()}",
        f"# based_on\n{locked_file}",
        f"# scene_purpose\n{validated.scene_purpose.strip()}",
        f"# required_information_gain\n{information_gain_block}",
        f"# required_plot_progress\n{validated.required_plot_progress.strip()}",
        f"# required_decision_shift\n{validated.required_decision_shift.strip()}",
        f"# avoid_motifs\n{avoid_motifs_block}",
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
    updated.pop("force_manual_intervention_reason", None)
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