import json
import re
from pathlib import Path
from typing import Any

import requests
from chapter_orchestrator import build_chapter_opening_task, get_start_progress, should_rollover_after_lock
from chapter_trackers import chapter_id_from_task_or_locked, load_tracker_bundle, update_trackers_on_lock
from deepseek_reviewer import resolve_api_key
from deepseek_supervisor import apply_supervisor_decision_to_reviewer_result, build_next_scene_task_content, build_task_content_from_supervisor_decision, is_supervisor_enabled, run_supervisor_decision, run_supervisor_next_scene_task, run_supervisor_rescue_draft, save_next_scene_task_plan, save_supervisor_decision, save_supervisor_rescue_record
from issue_filters import filter_shared_issues
from jsonschema import validate
from lock_gate import apply_lock_gate, save_lock_gate_report
from openai import OpenAI
from planning_bootstrap import run_planning_bootstrap
from prewrite_checks import build_prewrite_review, save_prewrite_review
from project_inputs import load_human_input, render_human_input_markdown
from review_models import RepairMode, ReviewStatus, build_repair_plan_path, build_review_result_path, build_structured_review_result, load_repair_plan, load_structured_review_result, save_repair_plan, save_structured_review_result, update_structured_review_status
from review_scene import review_scene_file
from revision_lineage import append_revision_lineage, build_revision_lineage_path, build_revision_lineage_summary, load_revision_lineage, should_trigger_manual_intervention
from runtime_config import load_runtime_config
from skill_audit import audit_skill_router_result, save_skill_audit_outputs
from skill_router import render_skill_router_markdown, route_writer_skills, save_skill_router_outputs
from story_state import update_story_state_on_lock
from writer_skills import build_selected_skill_sections


ROOT = Path(__file__).resolve().parent.parent
PROSE_REPAIR = "prose_repair"
STRUCTURAL_REPAIR = "structural_repair"


def read_text(rel_path: str) -> str:
    path = ROOT / rel_path
    return path.read_text(encoding="utf-8")


def save_text(rel_path: str, content: str) -> None:
    path = ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def clip_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[已截断]"


def clip_tail_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return "[前文已省略]\n\n" + text[-max_chars:]


def call_ollama(
    model: str,
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    num_ctx: int,
    temperature: float,
    timeout: int,
    num_predict: int,
) -> str:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "num_ctx": num_ctx,
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }

    print(f"正在请求 Ollama: {model} @ {base_url}")
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()

    data = response.json()
    return data["message"]["content"]


def should_validate_local_models(config: dict | None = None) -> bool:
    if not config:
        return True
    value = config.get("agent", {}).get("validate_local_models_on_start", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off"}
    return bool(value)


def fetch_ollama_model_names(base_url: str, timeout: int = 8) -> list[str]:
    url = f"{str(base_url).rstrip('/')}/api/tags"
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    models = data.get("models", []) if isinstance(data, dict) else []
    names: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def validate_local_model_endpoints(config: dict) -> None:
    if not should_validate_local_models(config):
        return

    roles = []
    for role_name in ["writer", "reviewer"]:
        role = config.get(role_name, {})
        provider = str(role.get("provider", "")).strip().lower()
        base_url = str(role.get("base_url", "")).strip()
        model = str(role.get("model", "")).strip()
        if provider == "deepseek" or not base_url or not model:
            continue
        roles.append((role_name, base_url, model))

    if not roles:
        return

    cached_models: dict[str, list[str]] = {}
    for role_name, base_url, model in roles:
        if base_url not in cached_models:
            try:
                cached_models[base_url] = fetch_ollama_model_names(base_url)
            except requests.exceptions.RequestException as error:
                raise ValueError(f"{role_name} 本地模型服务不可达：{base_url}；请先确认 Ollama 服务已启动。原始错误：{error}") from error

        available = cached_models[base_url]
        if model not in available:
            preview = "、".join(available[:12]) if available else "无"
            raise ValueError(
                f"{role_name} 配置的模型 `{model}` 不在 {base_url} 的已加载列表中。当前可见模型：{preview}"
            )

        print(f"本地模型预检通过：{role_name} -> {model} @ {base_url}")


def should_use_deepseek_writer(config: dict) -> bool:
    writer = config.get("writer", {})
    base_url = str(writer.get("base_url", "")).rstrip("/")
    model = str(writer.get("model", "")).strip()
    provider = str(writer.get("provider", "")).strip().lower()
    return provider == "deepseek" or (base_url == "https://api.deepseek.com" and model == "deepseek-chat")


def should_use_compact_writer_prompt(config: dict | None = None) -> bool:
    if not config:
        return False

    writer = config.get("writer", {})
    mode = str(writer.get("compact_prompt", "auto")).strip().lower()
    if mode in {"1", "true", "yes", "on", "compact"}:
        return True
    if mode in {"0", "false", "no", "off", "full"}:
        return False
    return not should_use_deepseek_writer(config)


def is_local_writer_mode(config: dict | None = None) -> bool:
    if not config:
        return False
    writer = config.get("writer", {})
    provider = str(writer.get("provider", "")).strip().lower()
    return provider not in {"", "deepseek"}


def is_local_reviewer_mode(config: dict | None = None) -> bool:
    if not config:
        return False
    reviewer = config.get("reviewer", {})
    provider = str(reviewer.get("provider", "")).strip().lower()
    return provider not in {"", "deepseek"}


def extract_openai_message_content(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        raise ValueError("writer 响应缺少 choices")

    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None) if message is not None else None
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = str(item.get("text", "")).strip()
                if text:
                    parts.append(text)
        if parts:
            return "\n".join(parts).strip()
    raise ValueError("writer 响应缺少 message.content")


def call_writer_model(
    config: dict,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float,
    num_predict: int,
) -> str:
    writer = config["writer"]
    if should_use_deepseek_writer(config):
        base_url = str(writer.get("base_url", "https://api.deepseek.com")).rstrip("/")
        api_key = resolve_api_key(
            str(writer.get("api_key", "")).strip() or None,
            str(writer.get("api_key_env", "")).strip() or None,
        )
        if not api_key:
            raise ValueError("writer 缺少 DeepSeek API key")

        client = OpenAI(api_key=api_key, base_url=base_url)
        print(f"正在请求 DeepSeek writer: {writer['model']} @ {base_url}")
        response = client.chat.completions.create(
            model=writer["model"],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=False,
            temperature=temperature,
            max_tokens=max(int(num_predict), 256),
            timeout=config["generation"]["request_timeout"],
        )
        return extract_openai_message_content(response)

    return call_ollama(
        model=writer["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=writer["base_url"],
        num_ctx=config["generation"]["write_num_ctx"],
        temperature=temperature,
        timeout=config["generation"]["request_timeout"],
        num_predict=num_predict,
    )


def preferred_length_override(config: dict) -> str | None:
    raw = str(config.get("generation", {}).get("preferred_length_override", "")).strip()
    return raw or None


def resolve_preferred_length(config: dict, task_text: str, explicit_value: str | None = None) -> str | None:
    override = preferred_length_override(config)
    if override:
        return override
    value = str(explicit_value or extract_markdown_field(task_text, "preferred_length") or "").strip()
    return value or None


def contains_forbidden_modern_terms(text: str) -> list[str]:
    forbidden_terms = [
        "便利店",
        "收银机",
        "霓虹灯",
        "玻璃橱窗",
        "数据",
        "格式化",
        "档案室",
        "运尸车",
        "红绿灯",
        "马路",
        "路灯",
        "出租车",
        "手机",
        "电梯",
        "监控",
    ]
    return [term for term in forbidden_terms if term in text]


def extract_markdown_field(task_text: str, field_name: str) -> str | None:
    pattern = rf"(?ms)^#\s*{re.escape(field_name)}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, task_text)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


def contains_script_style(text: str) -> list[str]:
    problems = []
    stripped = text.strip()

    # 1. 明确的“场景说明”式写法
    if re.search(r"[（(]\s*场景\s*[:：]", text):
        problems.append("出现“（场景：...）”式舞台说明")

    # 2. 明确的人名加冒号台词格式
    dialogue_lines = re.findall(r"(?m)^\s*[一-龥A-Za-z0-9_]{1,12}[:：]", text)
    if len(dialogue_lines) >= 2:
        problems.append("出现多行“人物名：对白”格式")

    # 3. 连续两行及以上纯括号舞台说明
    pure_parenthetical_lines = re.findall(r"(?m)^\s*[（(].*[)）]\s*$", text)
    if len(pure_parenthetical_lines) >= 2:
        problems.append("出现连续括号舞台说明")
    elif stripped.startswith(("（", "(")) and stripped.endswith(("）", ")")):
        inner = stripped[1:-1].strip()
        if inner and len(inner) >= 12:
            problems.append("整段文本为括号包裹的舞台说明")

    return problems


def contains_outline_style(text: str) -> list[str]:
    problems = []
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if not lines:
        return problems

    bullet_lines = [line for line in lines if re.match(r"^(?:[-*•]|\d+[.)])\s+", line)]
    heading_lines = [line for line in lines if re.match(r"^#{1,6}\s+\S+", line)]

    if len(bullet_lines) >= 3:
        problems.append("出现多行列表式提纲，不像连续小说正文")
    if len(heading_lines) >= 2:
        problems.append("出现多个标题分段，不像单段场景草稿")

    return problems


def is_likely_truncated(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False

    suspicious_endings = [
        "（",
        "(",
        "“",
        "\"",
        "：",
        ":",
        "——",
        "…",
        "「",
        "『",
        "，",
        ",",
    ]
    if any(stripped.endswith(x) for x in suspicious_endings):
        return True

    # 末尾如果明显像半截句，也算可疑
    if len(stripped) >= 1 and stripped[-1].isalnum():
        # 中文正文末尾没有句号不一定错，但结合长度太短时可疑
        if len(stripped) < 80:
            return True

    return False


def extract_forbidden_characters(task_text: str) -> list[str]:
    constraints = extract_markdown_field(task_text, "constraints") or ""
    blocked = []

    known_names = [
        "谢观鱼",
        "裴照骨",
        "净苦和尚",
        "阿绣",
    ]

    for name in known_names:
        patterns = [
            f"不要让{name}出场",
            f"不允许{name}出场",
            f"本场景不要让{name}出场",
            f"不要{name}出场",
        ]
        if any(p in constraints for p in patterns):
            blocked.append(name)

    return blocked


def detect_forbidden_characters(task_text: str, draft_text: str) -> list[str]:
    blocked = extract_forbidden_characters(task_text)
    return [name for name in blocked if name in draft_text]


EDITORIAL_HEADING_PATTERNS = [
    r"^[\t >#\-*]*(?:\*\*)?[【\[]?(?:修订说明|修改说明|说明|执行说明|推进说明|写作说明|改写说明|补充说明|内容说明|思路说明|本次说明)[】\]]?(?:\*\*)?\s*[:：]?\s*$",
    r"^[\t >#\-*]*(?:\*\*)?(?:以下为正文|以下正文|正文如下|以下是正文|以下是修改说明|以下是修订说明)(?:\*\*)?\s*[:：]?\s*$",
    r"^[\t >#\-*]*(?:\*\*)?(?:注|备注|附注)(?:\*\*)?\s*[:：].*$",
]


def contains_editorial_explanation(text: str) -> list[str]:
    markers = [
        "【修订说明】",
        "【修改说明】",
        "【说明】",
        "【执行说明】",
        "【推进说明】",
        "以下为",
        "以下正文",
        "正文如下",
        "改写说明",
        "修订说明",
        "执行说明",
        "推进说明",
        "写作说明",
        "注：",
        "备注：",
    ]
    found = [m for m in markers if m in text]
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(re.match(pattern, stripped, flags=re.IGNORECASE) for pattern in EDITORIAL_HEADING_PATTERNS):
            found.append(stripped)

    deduped: list[str] = []
    for item in found:
        if item not in deduped:
            deduped.append(item)
    return deduped


def build_validation_errors(task_text: str, draft_text: str) -> list[str]:
    errors = []
    if not str(draft_text).strip():
        errors.append("草稿为空，未生成有效小说正文")
        return errors

    modern_terms = contains_forbidden_modern_terms(draft_text)
    editorial_markers = contains_editorial_explanation(draft_text)
    if editorial_markers:
        errors.append(f"包含说明性附加文本，不属于小说正文: {editorial_markers}")
    if modern_terms:
        errors.append(f"包含不允许的现代词汇: {modern_terms}")

    script_style = contains_script_style(draft_text)
    if script_style:
        errors.append("文本呈现剧本体/分镜体痕迹，不符合小说正文要求")

    outline_style = contains_outline_style(draft_text)
    if outline_style:
        errors.append("文本呈现提纲/列表式格式，不符合小说正文要求")

    forbidden_characters = detect_forbidden_characters(task_text, draft_text)
    if forbidden_characters:
        errors.append(f"违反角色边界限制，出现了不应出场人物: {forbidden_characters}")

    if is_likely_truncated(draft_text):
        errors.append("草稿疑似被截断或结尾不完整")

    return errors

def build_relevant_character_section(task_text: str, character_bible: str) -> str:
    constraints = extract_markdown_field(task_text, "constraints") or ""

    allowed_names = ["孟浮灯"]
    if "老张头可以" in constraints or "老张头" in constraints:
        allowed_names.append("老张头")

    sections = []
    for name in allowed_names:
        pattern = rf"(?ms)^###\s*{re.escape(name)}\s*\n(.*?)(?=^###\s|\Z)"
        match = re.search(pattern, character_bible)
        if match:
            sections.append(f"### {name}\n{match.group(1).strip()}")

    if sections:
        return "\n\n".join(sections)

    # 如果没匹配到结构化人物段，就退化为短提示
    return "### 当前相关人物\n- 孟浮灯：本场核心视角人物\n- 老张头：可极轻出场的背景人物"


def load_story_state_snapshot() -> dict[str, Any] | None:
    path = ROOT / "03_locked/state/story_state.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def build_scene_contract_summary(task_text: str) -> str:
    goal = (extract_markdown_field(task_text, "goal") or "").strip()
    scene_purpose = (extract_markdown_field(task_text, "scene_purpose") or "").strip()
    information_gain = extract_markdown_list_field(task_text, "required_information_gain")
    plot_progress = (extract_markdown_field(task_text, "required_plot_progress") or "").strip()
    decision_shift = (extract_markdown_field(task_text, "required_decision_shift") or "").strip()
    required_state_change = extract_markdown_list_field(task_text, "required_state_change")
    avoid_motifs = extract_markdown_list_field(task_text, "avoid_motifs")

    lines = ["# 当前 scene contract"]
    if goal:
        lines.append(f"- 核心目标：{goal}")
    if scene_purpose:
        lines.append(f"- 场景功能：{scene_purpose}")
    if information_gain:
        lines.append(f"- 新信息要求：{'；'.join(information_gain[:3])}")
    if plot_progress:
        lines.append(f"- 局面推进要求：{plot_progress}")
    if decision_shift:
        lines.append(f"- 决策偏移要求：{decision_shift}")
    if required_state_change:
        lines.append(f"- 状态变化要求：{'；'.join(required_state_change[:3])}")
    if avoid_motifs:
        lines.append(f"- 避免复用：{'；'.join(avoid_motifs[:4])}")
    return "\n".join(lines)


def load_writer_tracker_bundle(task_text: str) -> dict[str, Any]:
    chapter_state_path = (extract_markdown_field(task_text, "chapter_state") or "").strip()
    chapter_state_text = ""
    if chapter_state_path:
        try:
            chapter_state_text = read_text(chapter_state_path)
        except FileNotFoundError:
            chapter_state_text = ""
    try:
        chapter_id = chapter_id_from_task_or_locked(task_text, "")
    except Exception:
        return {}
    try:
        return load_tracker_bundle(
            ROOT,
            chapter_id,
            chapter_state_text=chapter_state_text,
            story_state=load_story_state_snapshot(),
        )
    except Exception:
        return {}


def build_recent_scene_summaries_section(task_text: str) -> str:
    tracker_bundle = load_writer_tracker_bundle(task_text)
    chapter_progress = tracker_bundle.get("chapter_progress", {}) if isinstance(tracker_bundle, dict) else {}
    scene_summaries = chapter_progress.get("scene_summaries", []) if isinstance(chapter_progress, dict) else []
    if not isinstance(scene_summaries, list) or not scene_summaries:
        return ""

    lines = ["# 最近结构化场景摘要"]
    for item in scene_summaries[-3:]:
        if not isinstance(item, dict):
            continue
        scene_id = str(item.get("scene_id") or "").strip() or "unknown_scene"
        scene_function = str(item.get("scene_function") or "").strip() or "未标注功能"
        lines.append(f"- {scene_id}｜{scene_function}")

        new_information = [str(value).strip() for value in (item.get("new_information_items") or []) if str(value).strip()]
        if new_information:
            lines.append(f"  - 新信息：{'；'.join(new_information[:2])}")

        protagonist_decision = str(item.get("protagonist_decision") or "").strip()
        if protagonist_decision:
            lines.append(f"  - 新动作/决策：{protagonist_decision}")

        state_changes = [str(value).strip() for value in (item.get("state_changes") or []) if str(value).strip()]
        if state_changes:
            lines.append(f"  - 状态变化：{'；'.join(state_changes[:2])}")

        artifacts_changed = item.get("artifacts_changed", []) if isinstance(item.get("artifacts_changed"), list) else []
        if artifacts_changed:
            artifact_labels = [str(entry.get("label") or "").strip() for entry in artifacts_changed if isinstance(entry, dict) and str(entry.get("label") or "").strip()]
            if artifact_labels:
                lines.append(f"  - 物件变化：{'；'.join(artifact_labels[:2])}")
    return "\n".join(lines)


def build_writer_tracker_slices_section(task_text: str) -> str:
    tracker_bundle = load_writer_tracker_bundle(task_text)
    if not isinstance(tracker_bundle, dict) or not tracker_bundle:
        return ""

    chapter_progress = tracker_bundle.get("chapter_progress", {}) if isinstance(tracker_bundle.get("chapter_progress"), dict) else {}
    revelation_tracker = tracker_bundle.get("revelation_tracker", {}) if isinstance(tracker_bundle.get("revelation_tracker"), dict) else {}
    artifact_state = tracker_bundle.get("artifact_state", {}) if isinstance(tracker_bundle.get("artifact_state"), dict) else {}
    chapter_structure_summary = chapter_progress.get("chapter_structure_summary", {}) if isinstance(chapter_progress, dict) else {}

    lines = ["# 相关 tracker 摘要"]
    if chapter_progress:
        lines.append(f"- 章节目标：{str(chapter_progress.get('chapter_goal') or '').strip() or '未记录'}")
        lines.append(f"- 主角当前目标：{str(chapter_progress.get('protagonist_goal') or '').strip() or '未记录'}")
        lines.append(f"- 当前模式 / 调查阶段 / 风险：{str(chapter_progress.get('protagonist_mode') or '未记录')} / {str(chapter_progress.get('investigation_stage') or '未记录')} / {str(chapter_progress.get('risk_level') or '未记录')}")
        unresolved = [str(item).strip() for item in (chapter_progress.get("unresolved_questions") or []) if str(item).strip()]
        if unresolved:
            lines.append(f"- 当前未解问题：{'；'.join(unresolved[:3])}")
    if revelation_tracker:
        confirmed = [str(item).strip() for item in (revelation_tracker.get("confirmed_facts") or []) if str(item).strip()]
        suspected = [str(item).strip() for item in (revelation_tracker.get("suspected_facts") or []) if str(item).strip()]
        relationship_unknowns = [str(item).strip() for item in (revelation_tracker.get("relationship_unknowns") or []) if str(item).strip()]
        if confirmed:
            lines.append(f"- 已确认事实：{'；'.join(confirmed[:3])}")
        if suspected:
            lines.append(f"- 待验证事实：{'；'.join(suspected[:3])}")
        if relationship_unknowns:
            lines.append(f"- 暂未揭开的关系：{'；'.join(relationship_unknowns[:3])}")
    items = artifact_state.get("items", []) if isinstance(artifact_state, dict) else []
    artifact_lines: list[str] = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        holder = str(item.get("holder") or "待确认").strip() or "待确认"
        location = str(item.get("location") or "待确认").strip() or "待确认"
        visibility = str(item.get("visibility") or "unknown").strip() or "unknown"
        artifact_lines.append(f"{label}（持有者：{holder}；位置：{location}；可见性：{visibility}）")
    if artifact_lines:
        lines.append(f"- 关键物件切片：{'；'.join(artifact_lines)}")
    if chapter_structure_summary:
        lines.append(
            f"- 章节结构锚点：首个线索场={str(chapter_structure_summary.get('first_clue_scene_id') or '未记录')}；首个旧识暗示场={str(chapter_structure_summary.get('first_old_acquaintance_hint_scene_id') or '未记录')}；首个调查触发场={str(chapter_structure_summary.get('first_investigation_trigger_scene_id') or '未记录')}"
        )
    return "\n".join(lines)


def build_prose_reference_section(task_text: str) -> str:
    based_on_path = (extract_markdown_field(task_text, "based_on") or "").strip()
    if not based_on_path:
        return ""
    try:
        full_text = read_text(based_on_path)
    except FileNotFoundError:
        return "# 少量必要 prose 参考\n来源文件缺失，跳过旧稿参考。"
    paragraphs = [line.strip() for line in full_text.splitlines() if line.strip()]
    prose_seed = paragraphs[-1] if paragraphs else full_text.strip()
    based_on_text = clip_tail_text(prose_seed, 280)
    return f"# 少量必要 prose 参考\n来源文件：{based_on_path}\n- 仅用于承接声口与场面，不得顺着旧文风滑行，更不能照抄旧场气氛。\n\n{based_on_text}"


def get_scene_writing_skill_router_result(task_text: str) -> dict[str, Any]:
    output_target = (extract_markdown_field(task_text, "output_target") or "").strip()
    if output_target and not output_target.startswith("02_working/drafts/"):
        return {
            "phase": "scene_writing",
            "genre_tags": [],
            "trope_tags": [],
            "demand_tags": [],
            "selected_skills": [],
            "rejected_candidates": [],
            "risk_flags": ["non_draft_output_target"],
        }

    chapter_state = (extract_markdown_field(task_text, "chapter_state") or "").strip()
    state_signals: dict[str, Any] = {}
    if chapter_state:
        state_signals["has_chapter_state"] = True
    if (ROOT / "03_locked/state/story_state.json").exists():
        state_signals["has_story_state"] = True
    if (ROOT / "03_locked/state/trackers").exists():
        state_signals["has_trackers"] = True

    manifest_parts: list[str] = []
    for rel_path in ["00_manifest/novel_manifest.md", "00_manifest/world_bible.md"]:
        try:
            content = read_text(rel_path)
        except FileNotFoundError:
            content = ""
        if content.strip():
            manifest_parts.append(content)

    return route_writer_skills(
        phase="scene_writing",
        task_text=task_text,
        project_manifest_text="\n".join(manifest_parts),
        state_signals=state_signals,
    )


def build_scene_writing_skill_router_section(task_text: str) -> str:
    result = get_scene_writing_skill_router_result(task_text)
    saved = save_skill_router_outputs(
        ROOT,
        "02_working/planning/scene_writing_skill_router",
        result,
        heading="# scene writing skill router",
    )
    return f"# scene writing skill router\n来源文件：{saved['md_file']}\n\n" + read_text(saved["md_file"]).split("\n", 1)[1]


def build_selected_writer_skill_sections(task_text: str) -> str:
    result = get_scene_writing_skill_router_result(task_text)
    selected = result.get("selected_skills", [])
    if not selected:
        return ""
    return build_selected_skill_sections(ROOT, selected, heading_prefix="# writer skill")

def compile_context(config: dict) -> str:
    task_text_full = read_text("01_inputs/tasks/current_task.md")
    task_text = clip_text(task_text_full, 1600)
    novel_manifest = clip_text(read_text("00_manifest/novel_manifest.md"), 900)
    world_bible = clip_text(read_text("00_manifest/world_bible.md"), 700)
    character_bible_full = read_text("00_manifest/character_bible.md")
    relevant_characters = build_relevant_character_section(task_text, character_bible_full)
    life_notes = clip_text(read_text("01_inputs/life_notes/latest.md"), 800)

    chapter_state_path = extract_markdown_field(task_text, "chapter_state")
    chapter_state_section = ""

    if chapter_state_path:
        chapter_state_path = chapter_state_path.strip()
        try:
            chapter_state_text = clip_text(read_text(chapter_state_path), 1600)
            chapter_state_section = f"""

# 当前章节状态
来源文件：{chapter_state_path}

{chapter_state_text}
"""
        except FileNotFoundError:
            chapter_state_section = f"""

# 当前章节状态
来源文件：{chapter_state_path}

[警告：未找到该文件，无法载入章节状态]
"""

    prewrite_review = build_prewrite_review(
        ROOT,
        task_text_full,
        chapter_state_text=read_text(chapter_state_path.strip()) if chapter_state_path and (ROOT / chapter_state_path.strip()).exists() else "",
    )
    prewrite_review_file = save_prewrite_review(ROOT, prewrite_review)
    prewrite_review_text = clip_text(read_text(prewrite_review_file), 1400)
    planning_outputs = run_planning_bootstrap(
        ROOT,
        task_text_full,
        chapter_state_text=read_text(chapter_state_path.strip()) if chapter_state_path and (ROOT / chapter_state_path.strip()).exists() else "",
    )
    worldview_patch_text = clip_text(read_text(planning_outputs["worldview_patch_file"]), 1000)
    timeline_patch_text = clip_text(read_text(planning_outputs["timeline_patch_file"]), 1000)
    character_patch_text = clip_text(read_text(planning_outputs["character_patch_file"]), 900)
    outline_text = clip_text(read_text(planning_outputs["outline_file"]), 1000)
    state_machine_text = clip_text(read_text(planning_outputs["state_machine_file"]), 900)

    scene_contract_section = build_scene_contract_summary(task_text)
    recent_scene_summaries_section = build_recent_scene_summaries_section(task_text)
    tracker_slices_section = build_writer_tracker_slices_section(task_text)
    prose_reference_section = build_prose_reference_section(task_text)
    human_input_section = render_human_input_markdown(load_human_input(ROOT))
    planning_repair_brief_path = (extract_markdown_field(task_text_full, "planning_repair_brief") or "").strip()
    planning_repair_brief_section = ""
    planning_repair_brief_text = ""
    planning_repair_status_path = ""
    planning_repair_status_section = ""
    if planning_repair_brief_path:
        try:
            planning_repair_brief_text = read_text(planning_repair_brief_path)
            clipped_planning_repair_brief_text = clip_text(planning_repair_brief_text, 1000)
            planning_repair_brief_section = f"""

# planning repair brief
来源文件：{planning_repair_brief_path}

{clipped_planning_repair_brief_text}
"""
        except FileNotFoundError:
            planning_repair_brief_section = f"""

# planning repair brief
来源文件：{planning_repair_brief_path}

[警告：未找到该文件，无法载入 planning repair brief]
"""
    scene_writing_router_result = get_scene_writing_skill_router_result(task_text_full)
    scene_writing_router_saved = save_skill_router_outputs(
        ROOT,
        "02_working/planning/scene_writing_skill_router",
        scene_writing_router_result,
        heading="# scene writing skill router",
    )
    scene_writing_skill_router_section = f"# scene writing skill router\n来源文件：{scene_writing_router_saved['md_file']}\n\n" + read_text(scene_writing_router_saved["md_file"]).split("\n", 1)[1]
    if planning_repair_brief_path and planning_repair_brief_text:
        planning_repair_status_path = save_planning_repair_status(
            extract_markdown_field(task_text_full, "task_id") or "generated-task",
            planning_repair_brief_path,
            planning_repair_brief_text,
            planning_outputs,
            scene_writing_router_saved["md_file"],
        ) or ""
        if planning_repair_status_path:
            planning_repair_status_text = clip_text(read_text(planning_repair_status_path), 900)
            planning_repair_status_section = f"""

# planning repair status
来源文件：{planning_repair_status_path}

{planning_repair_status_text}
"""
    selected_writer_skill_sections = build_selected_writer_skill_sections(task_text_full)
    skill_audits = [
        audit_skill_router_result("planning_bootstrap", planning_outputs.get("planning_skill_router", {})),
        audit_skill_router_result("character_creation", planning_outputs.get("character_creation_skill_router", {})),
        audit_skill_router_result("timeline_bootstrap", planning_outputs.get("timeline_bootstrap_skill_router", {})),
        audit_skill_router_result("scene_writing", scene_writing_router_result),
    ]
    skill_audit_files = save_skill_audit_outputs(ROOT, "02_working/planning/skill_audit", skill_audits)
    skill_audit_text = clip_text(read_text(skill_audit_files["md_file"]), 1200)

    compiled = f"""# 写前诊断
来源文件：{prewrite_review_file}

{prewrite_review_text}

# planner/bootstrap agent
来源文件：{planning_outputs["state_machine_file"]}

{state_machine_text}

# 世界观补全 proposal
来源文件：{planning_outputs["worldview_patch_file"]}

{worldview_patch_text}

# 时间线补全 proposal
来源文件：{planning_outputs["timeline_patch_file"]}

{timeline_patch_text}

# 角色补全 proposal
来源文件：{planning_outputs["character_patch_file"]}

{character_patch_text}

# 章节工作大纲
来源文件：{planning_outputs["outline_file"]}

{outline_text}

{planning_repair_brief_section}

{planning_repair_status_section}

{scene_contract_section}

# 本次必须遵守的项目总纲
{novel_manifest}

# 本次相关世界设定
{world_bible}

# 本次相关人物设定
{relevant_characters}

# 人工输入总表
{human_input_section or "[未提供 human_input.yaml，当前主要依赖 manifest / task / state。]"}

# 本次生活素材使用规则
- 生活素材只能提取气氛、感官、情绪、节奏、意象
- 禁止直接搬运现代现实世界的具体物件或设施进入小说场景
- 如与小说世界冲突，必须优先服从小说设定

# 本次可借用的生活素材
{life_notes}{chapter_state_section}

{recent_scene_summaries_section}

{tracker_slices_section}

{scene_writing_skill_router_section}

{selected_writer_skill_sections}

# skill audit
来源文件：{skill_audit_files["md_file"]}

{skill_audit_text}

{prose_reference_section}
"""

    context_file = config["output"]["context_file"]
    save_text(context_file, compiled)
    return compiled


def generate_decision_json(config: dict, current_context: str) -> dict:
    schema = json.loads(read_text("prompts/output_schema.json"))
    task_text = read_text("01_inputs/tasks/current_task.md")
    task_id = extract_markdown_field(task_text, "task_id") or "draft-task"
    goal = extract_markdown_field(task_text, "goal") or "根据当前设定生成草稿"
    draft_file = extract_markdown_field(task_text, "output_target")
    based_on_path = extract_markdown_field(task_text, "based_on")

    if not draft_file:
        draft_dir = config["output"]["draft_dir"]
        draft_file = f"{draft_dir}/{task_id}.md"

    if not draft_file.startswith("02_working/drafts/"):
        raise ValueError("draft_file 非法，禁止写入非 working 区域")

    used_sources = [
        "01_inputs/tasks/current_task.md",
        config["output"]["context_file"],
    ]
    if based_on_path:
        used_sources.append(based_on_path)

    risks = [
        "当前草稿依赖整理后的上下文，可能遗漏设定书中的局部细节。",
        "若任务单未明确角色边界或场景目标，草稿需要人工复核是否越界。",
    ]

    constraints = extract_markdown_field(task_text, "constraints") or ""
    if "不展开完整世界观" in constraints:
        risks.append("本次任务限制世界观展开，草稿可能有意保持信息密度克制。")
    elif "不新增重要设定" in constraints or "不新增制度性设定" in constraints:
        risks.append("本次任务限制新增设定，草稿需要人工检查是否有偷渡设定的句子。")

    result = {
        "task_id": task_id,
        "goal": goal,
        "used_sources": used_sources,
        "risks": risks[:3],
        "next_action": "human_review",
        "draft_file": draft_file,
    }

    validate(instance=result, schema=schema)
    return result


def load_repair_guidance(task_text: str) -> tuple[str | None, str | None, list[str]]:
    repair_mode = extract_markdown_field(task_text, "repair_mode")
    repair_plan_path = extract_markdown_field(task_text, "repair_plan")
    repair_actions: list[str] = []

    if repair_plan_path:
        try:
            repair_plan = load_repair_plan(ROOT, extract_markdown_field(task_text, "task_id") or "generated-task")
            if not repair_mode:
                repair_mode = repair_plan.mode.value
            repair_actions = [action.instruction for action in repair_plan.actions]
        except Exception:
            repair_actions = []

    return repair_mode, repair_plan_path, repair_actions


def load_lock_gate_report(task_id: str) -> dict[str, Any] | None:
    normalized = str(task_id or "").strip()
    if not normalized:
        return None
    path = ROOT / f"03_locked/reports/{normalized}_lock_gate_report.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def has_state_transition_evidence(reviewer_result: dict[str, Any], lock_gate_report: dict[str, Any] | None = None) -> bool:
    information_gain = reviewer_result.get("information_gain", {}) if isinstance(reviewer_result, dict) else {}
    plot_progress = reviewer_result.get("plot_progress", {}) if isinstance(reviewer_result, dict) else {}
    character_decision = reviewer_result.get("character_decision", {}) if isinstance(reviewer_result, dict) else {}

    if bool(information_gain.get("has_new_information")):
        return True
    if bool(plot_progress.get("has_plot_progress")):
        return True
    if bool(character_decision.get("has_decision_or_behavior_shift")):
        return True

    checks = lock_gate_report.get("checks", []) if isinstance(lock_gate_report, dict) else []
    for check in checks:
        if not isinstance(check, dict):
            continue
        if str(check.get("name") or "") == "state_transition_evidence" and bool(check.get("passed")):
            return True
    return False


def choose_repair_focus(task_text: str, reviewer_result: dict[str, Any]) -> tuple[str, list[str]]:
    information_gain = reviewer_result.get("information_gain", {}) if isinstance(reviewer_result, dict) else {}
    plot_progress = reviewer_result.get("plot_progress", {}) if isinstance(reviewer_result, dict) else {}
    character_decision = reviewer_result.get("character_decision", {}) if isinstance(reviewer_result, dict) else {}
    task_id = extract_markdown_field(task_text, "task_id") or str(reviewer_result.get("task_id") or "").strip()
    required_state_change = extract_markdown_list_field(task_text, "required_state_change")
    lock_gate_report = load_lock_gate_report(task_id)
    reasons: list[str] = []

    if information_gain and information_gain.get("has_new_information") is False:
        reasons.append("缺少可验证的新信息")
    if plot_progress and plot_progress.get("has_plot_progress") is False:
        reasons.append("缺少明确的 plot progress")
    if character_decision and character_decision.get("has_decision_or_behavior_shift") is False:
        reasons.append("缺少可追踪的角色决策/行为偏移")
    if required_state_change and not has_state_transition_evidence(reviewer_result, lock_gate_report=lock_gate_report):
        reasons.append("required_state_change 尚未形成可验证落点")

    all_issue_text = "\n".join(
        [str(item).strip() for item in reviewer_result.get("major_issues", []) + reviewer_result.get("minor_issues", []) if str(item).strip()]
    )
    if any(marker in all_issue_text for marker in ["信息增量", "plot progress", "推进不足", "推进不够", "决策", "状态变化", "scene 功能", "scene_function", "功能失效"]):
        reasons.append("reviewer 明确指出了结构缺口")

    deduped: list[str] = []
    for item in reasons:
        if item not in deduped:
            deduped.append(item)
    if deduped:
        return STRUCTURAL_REPAIR, deduped
    return PROSE_REPAIR, []


def build_writer_repair_rules(repair_mode: str | None, repair_focus: str | None = None) -> list[str]:
    rules: list[str] = []
    if repair_focus == PROSE_REPAIR:
        rules.extend(
            [
                "本次是 prose repair，优先修复衔接、语言密度、节奏和表达不稳问题。",
                "尽量局部修改，不主动引入大结构变化。",
            ]
        )
    elif repair_focus == STRUCTURAL_REPAIR:
        rules.extend(
            [
                "本次是 structural repair，本轮目标不是把句子修顺，而是补齐结构缺口。",
                "允许补入一个关键动作、一个明确新事实、一个动作后果、一个结尾状态变化，或把 scene contract 的必要项补写落地。",
                "如果原段落承载不了这些结构补丁，允许重组相关段落或改写结尾，但不要越界新增主线、制度设定或无关人物。",
            ]
        )
    if repair_mode == RepairMode.local_fix.value:
        rules.extend(
            [
                "本次是局部修补，不要推倒整场重写。",
                "优先保留旧稿已经可用的段落、动作顺序和场景结构。",
                "只修 repair_plan 指向的问题段落与句子。",
            ]
        )
        return rules
    if repair_mode == RepairMode.partial_redraft.value:
        rules.extend(
            [
                "本次允许局部重写，但不要扩大成整场翻写。",
                "优先保留方向正确的场景骨架，只重写受影响的段落块。",
                "如果 repair_plan 未要求，不要更换场景地点、人物边界和核心推进方式。",
            ]
        )
        return rules
    if repair_mode == RepairMode.full_redraft.value:
        rules.extend(
            [
                "本次允许整场重写，但仍须严格围绕 repair_plan 的核心问题。",
                "重写时优先修复核心推进失败、约束冲突或场景功能错位。",
                "即使整场重写，也不要擅自新增设定、人物或主线外扩。",
            ]
        )
        return rules
    return rules


def build_writer_repair_section(task_text: str) -> str:
    repair_mode, repair_plan_path, repair_actions = load_repair_guidance(task_text)
    repair_focus = (extract_markdown_field(task_text, "repair_focus") or "").strip()
    if not repair_mode and not repair_focus and not repair_plan_path and not repair_actions:
        return ""

    lines = ["【修订执行计划】"]
    if repair_mode:
        lines.append(f"- repair_mode: {repair_mode}")
    if repair_focus:
        lines.append(f"- repair_focus: {repair_focus}")
    if repair_plan_path:
        lines.append(f"- repair_plan: {repair_plan_path}")

    mode_rules = build_writer_repair_rules(repair_mode, repair_focus=repair_focus)
    if mode_rules:
        lines.append("- 执行边界：")
        lines.extend([f"  - {item}" for item in mode_rules])

    if repair_actions:
        lines.append("- 必须优先处理的修订动作：")
        lines.extend([f"  - {item}" for item in repair_actions[:5]])

    return "\n".join(lines)


def extract_markdown_list_field(task_text: str, field_name: str) -> list[str]:
    raw_value = extract_markdown_field(task_text, field_name)
    if not raw_value:
        return []
    items: list[str] = []
    for line in raw_value.splitlines():
        cleaned = re.sub(r"^[-*]\s*", "", line).strip()
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items


def build_writer_structure_section(task_text: str) -> str:
    scene_purpose = (extract_markdown_field(task_text, "scene_purpose") or "").strip()
    information_gain = extract_markdown_list_field(task_text, "required_information_gain")
    plot_progress = (extract_markdown_field(task_text, "required_plot_progress") or "").strip()
    decision_shift = (extract_markdown_field(task_text, "required_decision_shift") or "").strip()
    required_state_change = extract_markdown_list_field(task_text, "required_state_change")
    avoid_motifs = extract_markdown_list_field(task_text, "avoid_motifs")

    if not any([scene_purpose, information_gain, plot_progress, decision_shift, required_state_change, avoid_motifs]):
        return ""

    lines = ["【本场结构硬约束】"]
    if scene_purpose:
        lines.append(f"- 场景功能：{scene_purpose}")
    if information_gain:
        lines.append("- 必须写出的新信息增量：")
        lines.extend([f"  - {item}" for item in information_gain])
    if plot_progress:
        lines.append(f"- 必须完成的局面推进：{plot_progress}")
    if decision_shift:
        lines.append(f"- 主角必须出现的新动作/决策偏移：{decision_shift}")
    if required_state_change:
        lines.append("- 本场必须落地的状态变化：")
        lines.extend([f"  - {item}" for item in required_state_change])
    if avoid_motifs:
        lines.append("- 本场避免原样复用的母题/触发物：")
        lines.extend([f"  - {item}" for item in avoid_motifs])
    lines.append("- 以上结构要求必须体现在正文事件里，不能只停留在情绪、气氛、回想或解释。")
    return "\n".join(lines)


def build_structural_task_fields(task_text: str, reviewer_result: dict) -> dict[str, Any]:
    scene_purpose = (extract_markdown_field(task_text, "scene_purpose") or "").strip()
    information_gain = extract_markdown_list_field(task_text, "required_information_gain")
    plot_progress = (extract_markdown_field(task_text, "required_plot_progress") or "").strip()
    decision_shift = (extract_markdown_field(task_text, "required_decision_shift") or "").strip()
    required_state_change = extract_markdown_list_field(task_text, "required_state_change")
    avoid_motifs = extract_markdown_list_field(task_text, "avoid_motifs")

    goal_text = strip_revision_prefix((extract_markdown_field(task_text, "goal") or "").strip())
    if not scene_purpose:
        if goal_text:
            scene_purpose = f"继续围绕“{goal_text}”推进，并在场景结束时形成新的可验证变化。"
        else:
            scene_purpose = "本场必须形成新的可验证变化，不能只延长上一场气氛或余波。"

    reviewer_info = reviewer_result.get("information_gain", {}) if isinstance(reviewer_result, dict) else {}
    reviewer_plot = reviewer_result.get("plot_progress", {}) if isinstance(reviewer_result, dict) else {}
    reviewer_decision = reviewer_result.get("character_decision", {}) if isinstance(reviewer_result, dict) else {}
    reviewer_motif = reviewer_result.get("motif_redundancy", {}) if isinstance(reviewer_result, dict) else {}

    if not information_gain:
        information_gain = [str(item).strip() for item in reviewer_info.get("new_information_items", []) if str(item).strip()]
    if not information_gain:
        information_gain = ["补充至少一个新的具体信息，优先落在物件状态、关系变化、风险条件或行动边界上。"]

    if not plot_progress:
        plot_progress = str(reviewer_plot.get("progress_reason") or "").strip()
    if not plot_progress:
        plot_progress = "场景结尾前必须形成新的局面推进，例如阻碍变化、关系变化、行动启动或新约束落地。"

    if not decision_shift:
        decision_shift = str(reviewer_decision.get("decision_detail") or "").strip()
    if not decision_shift:
        decision_shift = "主角必须做出新的现实动作或选择，并让这个动作改变他接下来怎么处理局面。"

    if not avoid_motifs:
        avoid_motifs = [str(item).strip() for item in reviewer_motif.get("repeated_motifs", []) if str(item).strip()]

    if not required_state_change:
        required_state_change = ["至少让一个状态变量发生变化：已知信息 / 角色判断 / 行动计划 / 风险等级 / 关系态势 / 物件位置或可见性。"]

    deduped_information_gain: list[str] = []
    for item in information_gain:
        if item not in deduped_information_gain:
            deduped_information_gain.append(item)

    deduped_avoid_motifs: list[str] = []
    for item in avoid_motifs:
        if item not in deduped_avoid_motifs:
            deduped_avoid_motifs.append(item)

    deduped_required_state_change: list[str] = []
    for item in required_state_change:
        if item not in deduped_required_state_change:
            deduped_required_state_change.append(item)

    return {
        "scene_purpose": scene_purpose,
        "required_information_gain": deduped_information_gain,
        "required_plot_progress": plot_progress,
        "required_decision_shift": decision_shift,
        "required_state_change": deduped_required_state_change,
        "avoid_motifs": deduped_avoid_motifs,
    }


def build_scene10_prompt_guardrails(task_text: str) -> str:
    lowered = task_text.lower()
    is_scene10_like = any(marker in lowered for marker in ["scene10", "scene 10", "ch01_scene10"])
    if not is_scene10_like:
        return ""

    lines = [
        "【scene10 专项防跑偏规则】",
        "- 本场禁止再次把“改结法”“多打一个结”“留下线头”“让红绳尾端继续露出”“让平安符/红绳本身成为最终停留结果”写成核心动作偏移。",
        "- 如果写到绳、结、线头、红绳、平安符，它们只能作为触发物或背景，不得再次成为本场真正的新动作结果。",
        "- 本场必须产出一种不同于 scene07/08/09 的新型轻微现实偏移，例如：顺手收起、没有立刻擦掉、额外确认、轻微避开、重新摆正、暂缓一个本可立即完成的收尾动作。",
        "- “阿绣”的影响必须落实到一次具体做活动作的轻微偏移，不能只停留在意象联想、旧物回想或再次处理绳结/线头。",
        "- 重点不是再留下一截东西，而是让孟浮灯在求活日常里，把一个本来会直接做完的小动作轻轻带偏。",
    ]
    return "\n".join(lines)


def is_scene10_like_task(task_text: str) -> bool:
    lowered = str(task_text).lower()
    return any(marker in lowered for marker in ["scene10", "scene 10", "ch01_scene10"])


def detect_scene10_old_pattern_reuse(draft_text: str) -> list[str]:
    text = str(draft_text)
    lowered = text.lower()
    problems: list[str] = []

    knot_markers = ["多打", "改结", "绕了个", "绕上去", "另绕", "缠了两圈", "打了个松松的环"]
    tail_markers = ["线头", "绳头", "绳尾", "尾端", "垂在那里", "留着", "没割", "没有割", "不割", "不剪"]
    charm_markers = ["红绳", "平安符"]

    if any(marker in text for marker in knot_markers):
        problems.append("再次回到改结/绕结类旧动作模式")
    if any(marker in text for marker in tail_markers):
        problems.append("再次回到留线头/留绳尾/不割绳尾类旧动作模式")
    if any(marker in text for marker in charm_markers) and any(marker in text for marker in ["垂", "晃", "露", "留"]):
        problems.append("再次让红绳或平安符本身成为最终停留结果")
    if "不是检查。只是停了一下" in text or "他就是绕了" in text or "是因为别的东西" in text:
        problems.append("重复使用前几轮 rescue 的句法骨架")
    if "rope tail" in lowered or "knot" in lowered:
        problems.append("出现英文绳结/绳尾旧模式描述")

    deduped: list[str] = []
    for item in problems:
        if item not in deduped:
            deduped.append(item)
    return deduped


def build_writer_user_prompt(task_text: str, current_context: str, decision: dict, config: dict | None = None) -> str:
    repair_section = build_writer_repair_section(task_text)
    structure_section = build_writer_structure_section(task_text)
    scene10_guardrails = build_scene10_prompt_guardrails(task_text)
    scene_writing_skill_router_section = build_scene_writing_skill_router_section(task_text)
    selected_writer_skill_sections = build_selected_writer_skill_sections(task_text)
    router_result = get_scene_writing_skill_router_result(task_text)
    selected_skill_names = [str(item.get("skill") or "").strip() for item in router_result.get("selected_skills", []) if str(item.get("skill") or "").strip()]
    selected_skill_summary = "、".join(selected_skill_names) if selected_skill_names else "无"
    repair_rules = build_writer_repair_rules(
        extract_markdown_field(task_text, "repair_mode"),
        repair_focus=extract_markdown_field(task_text, "repair_focus"),
    )
    repair_rule_lines = "\n".join([f"14. {item}" for item in repair_rules[:1]]) if repair_rules else ""

    if should_use_compact_writer_prompt(config):
        prompt = f"""请根据以下输入直接写出可保存的小说正文。

硬规则：
1. 只输出正文，不要标题、JSON、列表、说明、注释、修订说明。
2. 必须是连续 prose，不要剧本体、分镜体、人物名加冒号、整段括号说明。
3. 不能擅自新增人物、设定、制度、主线钩子；人物出场边界必须服从任务单。
4. 若任务单提供 `scene_purpose / required_information_gain / required_plot_progress / required_decision_shift / avoid_motifs`，必须落实成正文里的可见事件结果。
5. 不能只写气氛、回想、疲惫或 lingering 疑问；本场至少交出两项：新信息 / 新动作或决策 / 现实后果。
6. 结尾时至少一个状态变量必须变化：已知信息、判断、行动计划、风险、关系、物件位置或可见性。
7. 优先使用 current scene contract、chapter_state、scene summaries、tracker 切片，不要顺着旧文风空转。
8. 本轮启用的 writer skills：{selected_skill_summary}
9. 若启用了 `continuity-guard`，不要让物件位置、风险等级、调查阶段、关系态势或时间承接静默漂移。
{repair_rule_lines}

【任务单】
{task_text}

【当前上下文】
{current_context}

{repair_section}

{structure_section}

{scene_writing_skill_router_section}

{selected_writer_skill_sections}

{scene10_guardrails}

【决策信息】
{json.dumps(decision, ensure_ascii=False, indent=2)}
"""
    else:
        prompt = f"""请根据以下输入写出 Markdown 草稿正文。

要求：
1. 只输出 Markdown 正文
2. 不要输出 JSON
3. 不要输出 [JSON]
4. 不要输出 [MARKDOWN]
5. 不要写解释
6. 正文控制在任务要求范围内
7. 必须是小说正文 prose，不允许写成剧本、分镜、舞台说明
8. 如果任务限制了人物出场边界，必须严格服从
9. 如果任务要求不新增设定，就不要擅自发明制度规则或主线钩子
10. 不要写“以下为……”
11. 不要写“注：……”
12. 不要附带创作说明、改写说明、风格说明
13. 不要使用括号包裹整段说明文字
14. 如果任务单提供了结构字段，必须把“新信息增量、局面推进、决策偏移”真正写进正文事件，不能只写气氛、感受或回想
15. 如果任务单提供了 avoid_motifs，禁止原样复用这些母题/触发物；除非写出新的功能
16. 本场结尾时，至少一个状态变量必须与开头不同：已知信息、角色判断、行动计划、风险等级、关系态势、物件位置或可见性，至少命中其中一项
17. 本场至少要有一个动作带来现实后果；不允许整场只有感受、联想、疲惫、回忆、气味描写或 lingering 的疑问
18. 本场必须至少命中以下三项中的两项：一个可验证的新信息、一个可追踪的新动作或决策、一个会影响后续的现实后果
19. 禁止把“名字再次浮现、疑问沉入心里、身体疲惫蔓延、某物硌在胸口/掌心”当作推进完成；除非它同时伴随明确决定、新事实暴露、物件状态变化或关系变化
20. 如果正文没有交出新事实、新动作、新后果、新状态变化中的至少若干项，该稿就算未完成 task
21. 优先使用 current scene contract、latest chapter_state、recent structured scene summaries、revelation/artifact/chapter_progress 切片来完成任务；不要顺着旧 scene 正文的文风滑行
22. 本轮启用的 writer skills：{selected_skill_summary}
23. 若启用了 `continuity-guard`，不要让物件位置、风险等级、调查阶段、关系态势或时间承接静默漂移
{repair_rule_lines}
【任务单】
{task_text}

【当前上下文】
{current_context}

{repair_section}

{structure_section}

{scene_writing_skill_router_section}

{selected_writer_skill_sections}

{scene10_guardrails}

【决策信息】
{json.dumps(decision, ensure_ascii=False, indent=2)}
"""
    return prompt.replace("\n\n\n", "\n\n")


def generate_markdown_draft(config: dict, current_context: str, decision: dict) -> str:
    system_prompt = read_text("prompts/writer_system.md")
    task_text = read_text("01_inputs/tasks/current_task.md")
    writer_context_max_chars = int(config.get("generation", {}).get("writer_context_max_chars", 8000))
    writer_context = clip_text(current_context, writer_context_max_chars)
    user_prompt = build_writer_user_prompt(task_text, writer_context, decision, config=config)

    print("正在请求模型生成草稿，请稍候...")
    markdown_text = call_writer_model(
        config,
        system_prompt,
        user_prompt,
        temperature=config["generation"]["temperature"],
        num_predict=1000,
    )

    return markdown_text.strip()

def rewrite_script_to_prose(config: dict, current_context: str, bad_draft: str) -> str:
    system_prompt = """你是小说改写助手。
你的任务是把一段剧本体、分镜体、提纲体、列表式草稿或舞台说明式文字，改写为连续的小说正文 prose。
不要新增设定，不要新增角色，不要改变原场景的基本事件顺序。
只输出改写后的小说正文，不要解释。"""

    task_text = read_text("01_inputs/tasks/current_task.md")

    user_prompt = f"""请把下面这段文本改写成小说正文 prose。

要求：
1. 去掉标题
2. 去掉括号场景说明
3. 去掉“人物名：”格式
4. 改写成连续叙事段落
5. 不新增角色
6. 不新增制度设定
7. 不新增主线钩子
8. 保持任务约束
9. 只输出改写后的正文

【任务单】
{task_text}

【当前上下文】
{current_context}

【待改写文本】
{bad_draft}
"""

    print("检测到非 prose 草稿，正在尝试强制改写为小说正文...")
    rewritten = call_writer_model(
        config,
        system_prompt,
        user_prompt,
        temperature=0.2,
        num_predict=1200,
    )

    # return rewritten.strip()
    return clean_model_output(rewritten)

def extract_plain_prose(config: dict, current_context: str, bad_draft: str) -> str:
    system_prompt = """你是小说正文提纯助手。
你的任务不是重写剧情，而是从输入文本中提取可用的小说正文 prose。
删除标题、括号说明、人物名加冒号的台词格式、修订说明、执行说明、推进说明、注释、解释文字。
保留叙述段落，不新增设定，不新增角色，不改变原有事件顺序。
只输出提纯后的小说正文。
凡是带有“说明 / 注 / 备注 / 以下正文 / 正文如下 / 列表总结”的区块，一律视为污染并删除。"""

    task_text = read_text("01_inputs/tasks/current_task.md")

    user_prompt = f"""请把下面文本提纯为小说正文 prose。

要求：
1. 只保留小说正文段落
2. 删除标题
3. 删除括号场景说明
4. 删除“人物名：对白”格式
5. 删除修订说明、执行说明、推进说明、注释、解释文字
6. 不新增角色
7. 不新增设定
8. 不改变事件顺序
9. 只输出提纯后的正文
10. 如果文本里出现 `**修订说明**`、`【执行说明】`、`正文如下`、编号列表总结等元话语，必须从该处起全部删除

【任务单】
{task_text}

【当前上下文】
{current_context}

【待提纯文本】
{bad_draft}
"""

    print("改写仍失败，正在尝试提纯为纯正文...")
    refined = call_writer_model(
        config,
        system_prompt,
        user_prompt,
        temperature=0.1,
        num_predict=1200,
    )

    return clean_model_output(refined)


def continue_truncated_draft(config: dict, current_context: str, bad_draft: str) -> str:
    system_prompt = """你是小说续写修复助手。
你的任务不是重写整场，而是把一段明显半截、被截断的小说正文补完整。
要求：
1. 紧接现有文本继续写，不重复已给出的句子
2. 保持同一场景、同一视角、同一文风
3. 优先把当前动作写完整，并自然收束到一个完整结尾
4. 不新增设定，不新增角色，不扩展主线
5. 只输出补全后的完整正文，不要解释"""

    task_text = read_text("01_inputs/tasks/current_task.md")

    user_prompt = f"""请补全下面这段明显被截断的小说正文，使其成为一段可直接保存的完整草稿。

要求：
1. 保留已有内容不变
2. 从现有最后一句自然续写
3. 总体仍满足任务要求
4. 只输出补全后的完整正文

【任务单】
{task_text}

【当前上下文】
{current_context}

【待补全文本】
{bad_draft}
"""

    print("检测到草稿疑似截断，正在尝试自动续写补全...")
    continued = call_writer_model(
        config,
        system_prompt,
        user_prompt,
        temperature=0.2,
        num_predict=1200,
    )

    return clean_model_output(continued)


def repair_invalid_draft(config: dict, current_context: str, bad_draft: str, errors: list[str]) -> str:
    system_prompt = """你是小说草稿修复助手。
你的任务不是重写方向，而是在尽量保留现有内容与场景骨架的前提下，修掉明确的验收违规项。
要求：
1. 优先修复校验错误，不要擅自改变场景核心目标
2. 删除或替换不合规词汇、说明文字、错误格式、现代词、明显违规表达
3. 保持小说正文 prose 形式
4. 不新增角色，不新增设定，不扩展主线
5. 只输出修复后的正文
6. 严禁输出任何元话语或附加区块，例如：修订说明、执行说明、推进说明、说明、注、备注、以下正文、正文如下
7. 如果原文末尾带有说明区块，必须整段删除，不得保留标题、项目符号或总结语"""

    task_text = read_text("01_inputs/tasks/current_task.md")
    joined_errors = "\n".join(f"- {item}" for item in errors if str(item).strip())

    user_prompt = f"""请针对下面这些验收错误，定向修复当前草稿。

【必须修复的错误】
{joined_errors}

【任务单】
{task_text}

【当前上下文】
{current_context}

【待修复草稿】
{bad_draft}
"""

    print("检测到草稿存在验收违规，正在尝试自动定向修复...")
    repaired = call_writer_model(
        config,
        system_prompt,
        user_prompt,
        temperature=0.2,
        num_predict=1200,
    )

    return clean_model_output(repaired)


def should_force_prose_rewrite(errors: list[str]) -> bool:
    text = " ".join(str(item) for item in errors)
    markers = [
        "剧本体",
        "分镜体",
        "提纲/列表式",
        "说明性附加文本",
    ]
    return any(marker in text for marker in markers)


def build_writer_trace(
    *,
    provider: str,
    mode: str,
    fallbacks_used: list[str],
    initial_validation_errors: list[str],
    final_validation_errors: list[str],
) -> dict[str, Any]:
    deduped_fallbacks: list[str] = []
    for item in fallbacks_used:
        value = str(item).strip()
        if value and value not in deduped_fallbacks:
            deduped_fallbacks.append(value)

    return {
        "provider": str(provider or "").strip() or "unknown",
        "mode": str(mode or "draft").strip() or "draft",
        "fallbacks_used": deduped_fallbacks,
        "initial_validation_errors": [str(item).strip() for item in initial_validation_errors if str(item).strip()][:6],
        "final_validation_errors": [str(item).strip() for item in final_validation_errors if str(item).strip()][:6],
    }

def save_failed_draft(task_id: str, content: str, suffix: str = "failed") -> None:
    path = f"02_working/logs/{task_id}_{suffix}.md"
    save_text(path, content)
    print(f"已保存失败稿供检查: {path}")

def validate_draft(task_text: str, draft_text: str) -> None:
    errors = build_validation_errors(task_text, draft_text)
    if errors:
        joined = "；".join(errors)
        raise ValueError(f"草稿验收失败: {joined}")


def strip_standalone_stage_directions(text: str) -> str:
    lines = text.splitlines()
    cleaned_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if re.fullmatch(r"[（(][^\n]{0,200}[)）]", stripped):
            continue
        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
    return cleaned_text.strip()


def write_draft(config: dict, current_context: str) -> dict:
    task_text = read_text("01_inputs/tasks/current_task.md")
    decision = generate_decision_json(config, current_context)
    task_id = decision["task_id"]
    writer_provider = str(config.get("writer", {}).get("provider", "")).strip().lower() or "unknown"
    fallbacks_used: list[str] = []
    initial_validation_errors: list[str] = []

    raw_markdown_text = generate_markdown_draft(config, current_context, decision)
    markdown_text = clean_model_output(raw_markdown_text)

    if not markdown_text and raw_markdown_text.strip():
        fallbacks_used.append("clean_output_empty")
        save_failed_draft(task_id, raw_markdown_text, "first_failed_raw")
        rewritten = rewrite_script_to_prose(config, current_context, raw_markdown_text)
        fallbacks_used.append("rewrite_script_to_prose")
        save_failed_draft(task_id, rewritten, "rewritten_attempt")

        rewritten_errors = build_validation_errors(task_text, rewritten)
        if not rewritten_errors:
            markdown_text = rewritten
        else:
            save_failure_reason(task_id, "；".join(rewritten_errors), "rewritten_failed_reason")
            refined = extract_plain_prose(config, current_context, rewritten)
            fallbacks_used.append("extract_plain_prose")
            save_failed_draft(task_id, refined, "refined_attempt")

            refined_errors = build_validation_errors(task_text, refined)
            if refined_errors:
                save_failure_reason(task_id, "；".join(refined_errors), "refined_failed_reason")
                raise ValueError(f"草稿验收失败（提纯后仍不通过）: {'；'.join(refined_errors)}")

            markdown_text = refined

    errors = build_validation_errors(task_text, markdown_text)
    errors = build_validation_errors(task_text, markdown_text)
    if errors:
        initial_validation_errors = list(errors)
        save_failed_draft(task_id, markdown_text, "first_failed")
        save_failure_reason(task_id, "；".join(errors), "first_failed_reason")

        if any("草稿疑似被截断" in e for e in errors):
            continued = continue_truncated_draft(config, current_context, raw_markdown_text)
            fallbacks_used.append("continue_truncated_draft")
            save_failed_draft(task_id, continued, "continued_attempt")
            continued_errors = build_validation_errors(task_text, continued)
            if not continued_errors:
                markdown_text = continued
                errors = []
            else:
                save_failure_reason(task_id, "；".join(continued_errors), "continued_failed_reason")
                errors = continued_errors

        # 先处理纯说明性污染
        if all("说明性附加文本" in e for e in errors):
            markdown_text = clean_model_output(markdown_text)
            errors = build_validation_errors(task_text, markdown_text)

        # 第一层 fallback：所有明显非 prose 的输出，优先强制改写为正文
        if errors and should_force_prose_rewrite(errors):
            rewritten = rewrite_script_to_prose(config, current_context, markdown_text)
            fallbacks_used.append("rewrite_script_to_prose")
            save_failed_draft(task_id, rewritten, "rewritten_attempt")

            rewritten_errors = build_validation_errors(task_text, rewritten)
            if not rewritten_errors:
                markdown_text = rewritten
            else:
                save_failure_reason(task_id, "；".join(rewritten_errors), "rewritten_failed_reason")

                # 第二层 fallback：提纯正文
                refined = extract_plain_prose(config, current_context, rewritten)
                fallbacks_used.append("extract_plain_prose")
                save_failed_draft(task_id, refined, "refined_attempt")

                refined_errors = build_validation_errors(task_text, refined)
                if refined_errors:
                    save_failure_reason(task_id, "；".join(refined_errors), "refined_failed_reason")
                    print("提纯后验收失败，具体原因如下：")
                    for err in refined_errors:
                        print(f"- {err}")
                    raise ValueError(f"草稿验收失败（提纯后仍不通过）: {'；'.join(refined_errors)}")

                markdown_text = refined

        elif errors:
            repaired = repair_invalid_draft(config, current_context, raw_markdown_text, errors)
            fallbacks_used.append("repair_invalid_draft")
            save_failed_draft(task_id, repaired, "repaired_attempt")
            repaired_errors = build_validation_errors(task_text, repaired)
            if repaired_errors:
                save_failure_reason(task_id, "；".join(repaired_errors), "repaired_failed_reason")
                raise ValueError(f"草稿验收失败: {'；'.join(repaired_errors)}")
            markdown_text = repaired

    final_validation_errors = build_validation_errors(task_text, markdown_text)

    decision_file = f"02_working/reviews/{decision['task_id']}.json"
    draft_file = decision["draft_file"]

    save_text(decision_file, json.dumps(decision, ensure_ascii=False, indent=2))
    save_text(draft_file, markdown_text)

    print(f"已保存决策文件: {decision_file}")
    print(f"已保存草稿文件: {draft_file}")
    return {
        "task_text": task_text,
        "decision": decision,
        "decision_file": decision_file,
        "draft_file": draft_file,
        "writer_trace": build_writer_trace(
            provider=writer_provider,
            mode="draft_generated",
            fallbacks_used=fallbacks_used,
            initial_validation_errors=initial_validation_errors,
            final_validation_errors=final_validation_errors,
        ),
    }


def build_existing_draft_result(task_text: str) -> dict | None:
    task_id = extract_markdown_field(task_text, "task_id") or "generated-task"
    draft_file = extract_markdown_field(task_text, "output_target")
    if not draft_file:
        return None

    reviewer_json_path = f"02_working/reviews/{task_id}_reviewer.json"
    draft_path = ROOT / draft_file
    reviewer_path = ROOT / reviewer_json_path

    if not draft_path.exists():
        return None
    if reviewer_path.exists() and reviewer_path.stat().st_mtime >= draft_path.stat().st_mtime:
        return None

    decision_file = f"02_working/reviews/{task_id}.json"
    decision = {}
    if (ROOT / decision_file).exists():
        try:
            decision = json.loads(read_text(decision_file))
        except Exception:
            decision = {}

    return {
        "task_text": task_text,
        "decision": decision,
        "decision_file": decision_file,
        "draft_file": draft_file,
        "resume_only": True,
    }


def build_review_retry_needed_content(task_text: str, draft_file: str, error_message: str) -> str:
    task_id = extract_markdown_field(task_text, "task_id") or "unknown-task"
    lines = [
        f"# {task_id} 审稿重试提醒",
        "",
        f"- 当前草稿：{draft_file}",
        f"- 当前任务：{task_id}",
        f"- 失败原因：{error_message}",
        "",
        "## 建议处理",
        "- 优先直接重新运行 `python app/main.py`，系统会尝试复用当前草稿并重新审稿",
        "- 如果多次重试仍失败，再考虑人工检查服务端模型状态",
    ]
    return "\n".join(lines).strip() + "\n"

def clean_model_output(text: str) -> str:
    text = text.strip()

    # 删除开头常见说明行
    patterns_to_remove = [
        r"^（以下为.*?）\s*",
        r"^\(以下为.*?\)\s*",
        r"^以下为.*?\n",
        r"^Rewritten\s*[:：]?\s*",
        r"^改写后[:：]?\s*",
        r"^修订版[:：]?\s*",
        r"^\*\*.*?修订版.*?\*\*\s*",
        r"^【修订后场景】\s*",
        r"^【场景修订版】\s*",
        r"^【正文】\s*",
    ]

    for pattern in patterns_to_remove:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)

    # 遇到说明性标记，直接截断后面全部内容
    split_markers = [
        "【修订说明】",
        "【修改说明】",
        "【说明】",
        "【执行说明】",
        "【推进说明】",
        "执行说明",
        "推进说明",
        "修订说明",
        "修改说明",
        "正文如下",
        "以下正文",
        "\n注：",
        "\n（注：",
        "\n(注：",
    ]

    cut_positions = [text.find(marker) for marker in split_markers if text.find(marker) != -1]
    lines = text.splitlines()
    running_index = 0
    for line in lines:
        stripped = line.strip()
        if stripped and any(re.match(pattern, stripped, flags=re.IGNORECASE) for pattern in EDITORIAL_HEADING_PATTERNS):
            cut_positions.append(running_index)
            break
        running_index += len(line) + 1
    if cut_positions:
        text = text[:min(cut_positions)]

    text = strip_standalone_stage_directions(text)

    return text.strip()

def save_failure_reason(task_id: str, reason: str, suffix: str = "failure_reason") -> None:
    path = f"02_working/logs/{task_id}_{suffix}.txt"
    save_text(path, reason)
    print(f"已保存失败原因: {path}")


def normalize_issue_lines(issues: list[str]) -> list[str]:
    cleaned = []
    for item in issues:
        text = str(item).strip()
        if not text:
            continue
        cleaned.append(text)
    return cleaned


def get_filtered_reviewer_issues(reviewer_result: dict, task_text: str) -> tuple[list[str], list[str]]:
    major_issues = filter_shared_issues(list(reviewer_result.get("major_issues", [])), task_text=task_text)
    minor_issues = filter_shared_issues(list(reviewer_result.get("minor_issues", [])), task_text=task_text)
    return major_issues, minor_issues


def strip_revision_prefix(goal: str) -> str:
    prefixes = [
        "基于上一版草稿进行小修：",
        "基于上一版草稿进行重写：",
        "对上一版草稿进行小修：",
        "对上一版草稿进行重写：",
        "基于上一版草稿进行局部修补：",
        "基于上一版草稿进行局部重写：",
        "基于上一版草稿进行结构修复：",
        "基于上一版草稿进行结构重写：",
        "基于上一版草稿整体重写当前 scene：",
        "基于上一版草稿重新写作：",
    ]
    cleaned = goal.strip()
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True
    cleaned = re.sub(r"(?:。|\s)*本次重点解决：.*$", "", cleaned).strip()
    return cleaned


def sanitize_followup_constraints(constraints: str) -> str:
    lines = str(constraints or "").splitlines()
    cleaned_lines: list[str] = []
    skip_repair_action_lines = False

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if skip_repair_action_lines and stripped.startswith("-"):
            continue
        if skip_repair_action_lines and not stripped:
            skip_repair_action_lines = False
            continue
        if skip_repair_action_lines:
            skip_repair_action_lines = False

        if stripped.startswith("- 修订模式："):
            continue
        if stripped.startswith("- 修订焦点："):
            continue
        if stripped == "- structural_repair 触发原因：":
            skip_repair_action_lines = True
            continue
        if stripped == "- repair_plan 执行动作：":
            skip_repair_action_lines = True
            continue
        if stripped.startswith("- 额外修订要求"):
            continue
        if not stripped:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        cleaned_lines.append(line)

    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()
    return "\n".join(cleaned_lines).strip()


def extract_scene_number(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"scene(\d+)", str(text), re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def extract_chapter_number(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"ch(\d+)", str(text), re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def get_run_mode(config: dict) -> str:
    run = config.get("run", {})
    mode = str(run.get("mode") or "continue").strip().lower()
    return mode if mode in {"continue", "restart"} else "continue"


def should_skip_existing_draft_reuse(config: dict, loop_round: int) -> bool:
    return get_run_mode(config) == "restart" and loop_round == 1


def get_runtime_target_chapter(config: dict) -> int | None:
    run = config.get("run", {})
    value = run.get("target_chapter")
    if value in (None, "", 0):
        return None
    try:
        target = int(value)
    except (TypeError, ValueError):
        return None
    return target if target > 0 else None


def get_runtime_target_scene(config: dict) -> int | None:
    run = config.get("run", {})
    value = run.get("target_scene")
    if value not in (None, "", 0):
        try:
            target = int(value)
        except (TypeError, ValueError):
            return None
        return target if target > 0 else None

    generation = config.get("generation", {})
    legacy_value = generation.get("auto_continue_until_scene")
    if legacy_value in (None, "", 0):
        return None
    try:
        target = int(legacy_value)
    except (TypeError, ValueError):
        return None
    return target if target > 0 else None


def extract_task_progress(task_text: str) -> tuple[int | None, int | None]:
    output_target = extract_markdown_field(task_text, "output_target") or ""
    return extract_chapter_number(output_target or task_text), extract_scene_number(output_target or task_text)


def latest_locked_file_for_bootstrap(start_chapter: int) -> str | None:
    chapter_dir = ROOT / "03_locked/chapters"
    if not chapter_dir.exists():
        return None
    candidates: list[tuple[tuple[int, int], Path]] = []
    for path in chapter_dir.glob("ch*_scene*.md"):
        chapter_number = extract_chapter_number(path.name)
        scene_number = extract_scene_number(path.name)
        if chapter_number is None or scene_number is None:
            continue
        if chapter_number > start_chapter:
            continue
        candidates.append(((chapter_number, scene_number), path))
    if not candidates:
        return None
    return str(sorted(candidates, key=lambda item: item[0])[-1][1].relative_to(ROOT).as_posix())


def prepare_runtime_start(config: dict) -> str | None:
    if get_run_mode(config) != "restart":
        return None

    run = config.get("run", {})
    restart_from_task = str(run.get("restart_from_task") or "").strip()
    if restart_from_task:
        task_text = read_text(restart_from_task)
        save_text("01_inputs/tasks/current_task.md", task_text)
        return extract_markdown_field(task_text, "task_id") or restart_from_task

    start_chapter, start_scene = get_start_progress(config)
    task_id, task_text = build_chapter_opening_task(
        ROOT,
        config,
        chapter_number=start_chapter,
        scene_number=start_scene,
        previous_locked_file=latest_locked_file_for_bootstrap(start_chapter),
    )
    save_text("01_inputs/tasks/current_task.md", task_text)
    task_file = f"01_inputs/tasks/generated/{task_id}.md"
    save_text(task_file, task_text)
    return task_id


def should_continue_after_lock(config: dict, next_scene_task_file: str | None) -> bool:
    if not next_scene_task_file:
        return False
    target_chapter = get_runtime_target_chapter(config)
    target_scene = get_runtime_target_scene(config)
    if target_chapter is None and target_scene is None:
        return False
    task_text = read_text(next_scene_task_file)
    next_chapter_number, next_scene_number = extract_task_progress(task_text)
    if next_scene_number is None and next_chapter_number is None:
        return False
    if target_chapter is not None:
        if next_chapter_number is None:
            return False
        if next_chapter_number < target_chapter:
            return True
        if next_chapter_number > target_chapter:
            return False
        if target_scene is None:
            return True
    if target_scene is None:
        return False
    if next_scene_number is None:
        return False
    return next_scene_number <= target_scene


def is_supervisor_rescue_draft_enabled(config: dict) -> bool:
    generation = config.get("generation", {})
    value = generation.get("supervisor_rescue_draft_enabled", True)
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off"}
    return bool(value)


def is_problem_like_issue(text: str) -> bool:
    text = str(text).strip()
    if not text:
        return False

    problem_markers = [
        "未完成",
        "不足",
        "不够",
        "偏弱",
        "偏空",
        "过满",
        "越界",
        "失衡",
        "过多",
        "不明确",
        "不清晰",
        "未能",
        "没有形成",
        "不充分",
        "缺少",
        "缺乏",
        "太满",
        "太散",
        "太重",
        "太轻",
        "闭环感弱",
        "闭环偏弱",
        "牵引力不够",
        "动作牵引不够",
    ]
    pure_constraint_markers = [
        "No new characters",
        "保持单视角",
        "不引入新人物",
        "不新增制度性设定",
        "只允许孟浮灯作为核心视角人物",
        "不引入谢观鱼",
        "不引入裴照骨",
        "不引入净苦和尚",
    ]

    if any(marker in text for marker in pure_constraint_markers):
        return False

    return any(marker in text for marker in problem_markers)


def filter_followup_issue_lines(issues: list[str]) -> list[str]:
    return [text for text in normalize_issue_lines(issues) if is_problem_like_issue(text)]


def filter_usable_issues(issues: list[str]) -> list[str]:
    bad_exact = {
        "No new characters.",
        "No new characters",
        "不引入新人物。",
        "不新增制度性设定。",
        "保持单视角。",
    }

    cleaned = []
    for issue in issues:
        text = str(issue).strip()
        if not text:
            continue
        if text in bad_exact:
            continue
        if "No new characters" in text:
            continue
        if "Must not" in text or "The task:" in text:
            continue
        if "We need to check" in text or "But maybe" in text or "So maybe" in text:
            continue
        cleaned.append(text)
    return cleaned


def normalize_constraint_text(text: str) -> str:
    text = str(text).strip()
    text = re.sub(r"^[#\-\*\d\.\s]+", "", text)
    text = re.sub(r"[：:；;，,。.!！?？\s]+", "", text)
    return text


def dedupe_followup_issue_lines(original_constraints: str, issue_lines: list[str]) -> list[str]:
    original_lines = [
        normalize_constraint_text(line)
        for line in original_constraints.splitlines()
        if line.strip()
    ]

    deduped: list[str] = []
    seen_normalized: set[str] = set()

    for issue in issue_lines:
        normalized_issue = normalize_constraint_text(issue)
        if not normalized_issue:
            continue
        if normalized_issue in seen_normalized:
            continue
        if any(
            normalized_issue == original
            or normalized_issue in original
            or original in normalized_issue
            for original in original_lines
            if original
        ):
            continue
        deduped.append(issue)
        seen_normalized.add(normalized_issue)

    return deduped


def extract_skill_audit_phase_issues(reviewer_result: dict) -> dict[str, list[str]]:
    phase_issues: dict[str, list[str]] = {}
    for issue in list(reviewer_result.get("major_issues", [])) + list(reviewer_result.get("minor_issues", [])):
        text = str(issue).strip()
        if not text.startswith("[skill audit]["):
            continue
        match = re.match(r"^\[skill audit\]\[([^\]]+)\]\s*(.+)$", text)
        if not match:
            continue
        phase = match.group(1).strip()
        message = match.group(2).strip()
        if not phase or not message:
            continue
        phase_issues.setdefault(phase, [])
        if message not in phase_issues[phase]:
            phase_issues[phase].append(message)
    return phase_issues


def build_skill_audit_repair_hints(reviewer_result: dict) -> list[str]:
    phase_issues = extract_skill_audit_phase_issues(reviewer_result)
    hints: list[str] = []

    if "planning_bootstrap" in phase_issues:
        hints.append(
            "先核对 `02_working/planning/worldview_patch.md`、`02_working/outlines/chapter_outline` 与 `planning_bootstrap_skill_router.json`，修正 worldbuilding / scene-outline 的选择或产物，再继续改正文。"
        )
    if "character_creation" in phase_issues:
        hints.append(
            "先核对 `02_working/planning/character_patch.md` 与 `character_creation_skill_router.json`，修正角色功能卡或命名槽位，再继续改正文。"
        )
    if "timeline_bootstrap" in phase_issues:
        hints.append(
            "先核对 `02_working/planning/timeline_patch.md` 与 `timeline_bootstrap_skill_router.json`，修正章节时间承接和历史锚点，再继续改正文。"
        )
    if "scene_writing" in phase_issues:
        hints.append(
            "正文修订前先核对 `scene_writing_skill_router.json` 的 selected_skills，确保 `continuity-guard` 等必要 skill 已正确挂载。"
        )

    return hints


def build_planning_repair_targets(reviewer_result: dict) -> list[dict[str, str]]:
    phase_issues = extract_skill_audit_phase_issues(reviewer_result)
    targets: list[dict[str, str]] = []

    phase_specs = {
        "planning_bootstrap": {
            "label": "planning bootstrap",
            "artifact": "02_working/planning/worldview_patch.md",
            "router": "02_working/planning/planning_bootstrap_skill_router.json",
            "focus": "重建 worldbuilding / scene-outline 的 bootstrap 产物，并同步核对章节 outline。",
        },
        "character_creation": {
            "label": "character creation",
            "artifact": "02_working/planning/character_patch.md",
            "router": "02_working/planning/character_creation_skill_router.json",
            "focus": "重建角色功能卡、命名槽位与角色补全 proposal，再继续正文修订。",
        },
        "timeline_bootstrap": {
            "label": "timeline bootstrap",
            "artifact": "02_working/planning/timeline_patch.md",
            "router": "02_working/planning/timeline_bootstrap_skill_router.json",
            "focus": "重建章节时间承接、历史锚点与 timeline proposal，再继续正文修订。",
        },
        "scene_writing": {
            "label": "scene writing",
            "artifact": "02_working/planning/scene_writing_skill_router.md",
            "router": "02_working/planning/scene_writing_skill_router.json",
            "focus": "先纠正 scene_writing 的 selected_skills，再进行正文修订。",
        },
    }

    for phase in ["planning_bootstrap", "character_creation", "timeline_bootstrap", "scene_writing"]:
        issues = phase_issues.get(phase, [])
        if not issues:
            continue
        spec = phase_specs[phase]
        targets.append(
            {
                "phase": phase,
                "label": spec["label"],
                "artifact": spec["artifact"],
                "router": spec["router"],
                "focus": spec["focus"],
                "issues": "；".join(issues[:3]),
            }
        )

    return targets


def save_planning_repair_brief(task_id: str, reviewer_result: dict) -> str | None:
    targets = build_planning_repair_targets(reviewer_result)
    if not targets:
        return None

    rel_path = f"02_working/planning/{task_id}_planning_repair.md"
    lines = [
        "# planning repair brief",
        "",
        f"- task_id：{task_id}",
        "- 说明：本文件由 skill audit 自动生成，用于指导修订前先重建 planning working 资产。",
        "",
        "## repair order",
        "1. 先修复下列 planning / routing 资产。",
        "2. 确认 skill router 与 working proposal 已一致。",
        "3. 再根据修复后的 planning 资产继续正文修订。",
        "",
        "## repair targets",
    ]

    for item in targets:
        lines.extend(
            [
                f"### {item['phase']}",
                f"- focus：{item['focus']}",
                f"- artifact：{item['artifact']}",
                f"- router：{item['router']}",
                f"- source_issue：{item['issues']}",
                "",
            ]
        )

    save_text(rel_path, "\n".join(lines).strip() + "\n")
    return rel_path


def parse_planning_repair_brief_phases(brief_text: str) -> list[str]:
    phases: list[str] = []
    for line in str(brief_text or "").splitlines():
        match = re.match(r"^\s*###\s+([A-Za-z0-9_\-]+)\s*$", line.strip())
        if not match:
            continue
        phase = match.group(1).strip()
        if phase and phase not in phases:
            phases.append(phase)
    return phases


def save_planning_repair_status(
    task_id: str,
    planning_repair_brief_path: str,
    planning_repair_brief_text: str,
    planning_outputs: dict[str, Any],
    scene_writing_router_md_file: str,
) -> str | None:
    phases = parse_planning_repair_brief_phases(planning_repair_brief_text)
    if not phases:
        return None

    phase_artifacts: dict[str, list[str]] = {
        "planning_bootstrap": [
            planning_outputs["worldview_patch_file"],
            planning_outputs["outline_file"],
            planning_outputs["planning_skill_router_md_file"],
        ],
        "character_creation": [
            planning_outputs["character_patch_file"],
            planning_outputs["character_creation_skill_router_md_file"],
        ],
        "timeline_bootstrap": [
            planning_outputs["timeline_patch_file"],
            planning_outputs["timeline_bootstrap_skill_router_md_file"],
        ],
        "scene_writing": [
            scene_writing_router_md_file,
            "02_working/planning/scene_writing_skill_router.json",
        ],
    }

    rel_path = f"02_working/planning/{task_id}_planning_repair_status.md"
    lines = [
        "# planning repair status",
        "",
        f"- task_id：{task_id}",
        f"- source_brief：{planning_repair_brief_path}",
        "- 说明：检测到 planning_repair_brief 后，系统已自动重建相关 working 资产并在此登记。",
        "",
        "## rebuilt phases",
    ]

    for phase in phases:
        artifacts = phase_artifacts.get(phase, [])
        lines.append(f"### {phase}")
        if artifacts:
            lines.extend([f"- refreshed_artifact：{artifact}" for artifact in artifacts])
        else:
            lines.append("- refreshed_artifact：当前 phase 没有可登记的 working 资产。")
        lines.append("")

    save_text(rel_path, "\n".join(lines).strip() + "\n")
    return rel_path


def build_followup_task_id(task_id: str, mode: str) -> str:
    base = re.sub(r"-(?:R\d+|RW\d+)+$", "", task_id)
    revise_match = re.search(r"-R(\d+)$", task_id)
    rewrite_match = re.search(r"-RW(\d+)$", task_id)
    if mode == "revise":
        next_number = int(revise_match.group(1)) + 1 if revise_match else 1
        return f"{base}-R{next_number}"
    if mode == "rewrite":
        next_number = int(rewrite_match.group(1)) + 1 if rewrite_match else 1
        return f"{base}-RW{next_number}"
    return f"{base}-R1"


def build_followup_output_target(draft_file: str, mode: str) -> str:
    path = Path(draft_file)
    stem = path.stem

    if mode == "rewrite":
        rewrite_match = re.search(r"^(.*?)(_rewrite(?:\d+)?)$", stem)
        if rewrite_match:
            base_stem = rewrite_match.group(1)
            suffix = rewrite_match.group(2)
            number_match = re.search(r"_rewrite(\d+)$", suffix)
            if number_match:
                next_number = int(number_match.group(1)) + 1
                stem = f"{base_stem}_rewrite{next_number}"
            else:
                stem = f"{base_stem}_rewrite2"
        else:
            stem = f"{stem}_rewrite"
    else:
        version_matches = re.findall(r"_v(\d+)", stem)
        if version_matches:
            base_stem = re.sub(r"(?:_v\d+)+$", "", stem)
            next_version = int(version_matches[-1]) + 1
            stem = f"{base_stem}_v{next_version}"
        else:
            stem = f"{stem}_v2"

    return path.with_name(f"{stem}{path.suffix}").as_posix()


def build_followup_goal(original_goal: str, reviewer_result: dict, mode: str, task_text: str, repair_mode: str | None = None, repair_focus: str | None = None, repair_instructions: list[str] | None = None) -> str:
    base_goal = strip_revision_prefix(original_goal)
    summary = str(reviewer_result.get("summary", "")).strip()
    filtered_major, filtered_minor = get_filtered_reviewer_issues(reviewer_result, task_text)
    major_issues = filter_usable_issues(filtered_major)
    minor_issues = filter_usable_issues(filtered_minor)
    issues = filter_followup_issue_lines(
        major_issues + minor_issues
    )

    if repair_focus == STRUCTURAL_REPAIR and mode == "rewrite":
        prefix = "基于上一版草稿进行结构重写"
    elif repair_focus == STRUCTURAL_REPAIR:
        prefix = "基于上一版草稿进行结构修复"
    elif mode == "rewrite":
        prefix = "基于上一版草稿重新写作"
    elif repair_mode == RepairMode.local_fix.value:
        prefix = "基于上一版草稿进行局部修补"
    elif repair_mode == RepairMode.partial_redraft.value:
        prefix = "基于上一版草稿进行局部重写"
    elif repair_mode == RepairMode.full_redraft.value:
        prefix = "基于上一版草稿整体重写当前 scene"
    else:
        prefix = "基于上一版草稿进行小修"

    normalized_summary = normalize_constraint_text(summary)
    deduped_issues = []
    for issue in issues[:3]:
        normalized_issue = normalize_constraint_text(issue)
        if normalized_summary and normalized_issue:
            if (
                normalized_issue == normalized_summary
                or normalized_issue in normalized_summary
                or normalized_summary in normalized_issue
            ):
                continue
        deduped_issues.append(issue)

    if repair_instructions:
        issue_text = "；".join(repair_instructions[:3])
    else:
        issue_text = "；".join(deduped_issues) if deduped_issues else summary
    skill_hints = build_skill_audit_repair_hints(reviewer_result)
    if skill_hints:
        hint_prefix = "；".join(skill_hints[:2])
        if issue_text:
            issue_text = f"{hint_prefix}；{issue_text}"
        else:
            issue_text = hint_prefix
    if issue_text:
        return f"{prefix}：{base_goal}。本次重点解决：{issue_text}"
    return f"{prefix}：{base_goal}。"


def build_followup_constraints(task_text: str, reviewer_result: dict, repair_mode: str | None = None, repair_focus: str | None = None, repair_focus_reasons: list[str] | None = None, repair_instructions: list[str] | None = None) -> str:
    original_constraints = sanitize_followup_constraints(extract_markdown_field(task_text, "constraints") or "")
    filtered_major, filtered_minor = get_filtered_reviewer_issues(reviewer_result, task_text)
    major_issues = filter_usable_issues(filtered_major)
    minor_issues = filter_usable_issues(filtered_minor)
    issue_lines = filter_followup_issue_lines(
        major_issues + minor_issues
    )
    issue_lines = dedupe_followup_issue_lines(original_constraints, issue_lines)

    blocks = []
    if original_constraints:
        blocks.append(original_constraints)

    if repair_mode:
        blocks.append(f"- 修订模式：{repair_mode}")
    if repair_focus:
        blocks.append(f"- 修订焦点：{repair_focus}")
        if repair_focus == STRUCTURAL_REPAIR:
            blocks.append("- structural_repair 允许动作：")
            blocks.append("- 允许补入一个关键动作、新事实、动作后果或结尾状态变化。")
            blocks.append("- 必须把 scene contract 缺失项补写落地，不能只做语言微修。")
            if repair_focus_reasons:
                blocks.append("- structural_repair 触发原因：")
                blocks.extend([f"- {item}" for item in repair_focus_reasons[:4]])
        elif repair_focus == PROSE_REPAIR:
            blocks.append("- prose_repair 约束：优先修衔接、语言密度、节奏与表达稳定性，尽量不改大结构。")

    skill_hints = build_skill_audit_repair_hints(reviewer_result)
    if skill_hints:
        blocks.append("- skill audit 纠偏优先级：")
        blocks.extend([f"- {item}" for item in skill_hints[:4]])

    if repair_instructions:
        blocks.append("- repair_plan 执行动作：")
        blocks.extend([f"- {item}" for item in repair_instructions[:5]])
    elif issue_lines:
        blocks.append("- 额外修订要求：")
        blocks.extend([f"- {line}" for line in issue_lines])
    else:
        summary = str(reviewer_result.get("summary", "")).strip()
        if summary:
            blocks.append(f"- 额外修订要求：{summary}")

    return "\n".join(blocks).strip()


def build_generated_task_content(task_text: str, reviewer_result: dict, draft_file: str, mode: str, config: dict | None = None) -> str:
    task_id = extract_markdown_field(task_text, "task_id") or "generated-task"
    original_goal = extract_markdown_field(task_text, "goal") or "根据 reviewer 结果继续处理当前草稿"
    chapter_state = extract_markdown_field(task_text, "chapter_state")
    preferred_length = resolve_preferred_length(config or {}, task_text)
    repair_mode = None
    repair_focus = None
    repair_plan_path = None
    repair_instructions: list[str] = []
    repair_focus_reasons: list[str] = []

    if mode == "revise":
        task_id_for_plan = extract_markdown_field(task_text, "task_id") or "generated-task"
        repair_plan_path = build_repair_plan_path(task_id_for_plan)
        try:
            repair_plan = load_repair_plan(ROOT, task_id_for_plan)
            repair_mode = repair_plan.mode.value
            repair_instructions = [action.instruction for action in repair_plan.actions]
        except Exception:
            repair_plan_path = None

    repair_focus, repair_focus_reasons = choose_repair_focus(task_text, reviewer_result)

    new_task_id = build_followup_task_id(task_id, mode)
    planning_repair_brief_path = save_planning_repair_brief(new_task_id, reviewer_result)
    new_goal = build_followup_goal(
        original_goal,
        reviewer_result,
        mode,
        task_text,
        repair_mode=repair_mode,
        repair_focus=repair_focus,
        repair_instructions=repair_instructions,
    )
    new_constraints = build_followup_constraints(
        task_text,
        reviewer_result,
        repair_mode=repair_mode,
        repair_focus=repair_focus,
        repair_focus_reasons=repair_focus_reasons,
        repair_instructions=repair_instructions,
    )
    new_output_target = build_followup_output_target(draft_file, mode)
    structural_fields = build_structural_task_fields(task_text, reviewer_result)
    information_gain_block = "\n".join(f"- {item}" for item in structural_fields["required_information_gain"])
    state_change_block = "\n".join(f"- {item}" for item in structural_fields["required_state_change"])
    avoid_motifs_block = "\n".join(f"- {item}" for item in structural_fields["avoid_motifs"])

    sections = [
        f"# task_id\n{new_task_id}",
        f"# goal\n{new_goal}",
        f"# based_on\n{draft_file}",
        f"# scene_purpose\n{structural_fields['scene_purpose']}",
        f"# required_information_gain\n{information_gain_block}",
        f"# required_plot_progress\n{structural_fields['required_plot_progress']}",
        f"# required_decision_shift\n{structural_fields['required_decision_shift']}",
        f"# required_state_change\n{state_change_block}",
    ]

    if avoid_motifs_block:
        sections.append(f"# avoid_motifs\n{avoid_motifs_block}")

    if chapter_state:
        sections.append(f"# chapter_state\n{chapter_state}")

    if repair_mode:
        sections.append(f"# repair_mode\n{repair_mode}")
    if repair_focus:
        sections.append(f"# repair_focus\n{repair_focus}")

    if repair_plan_path:
        sections.append(f"# repair_plan\n{repair_plan_path}")

    if planning_repair_brief_path:
        sections.append(f"# planning_repair_brief\n{planning_repair_brief_path}")

    review_trace_summary = format_review_trace_summary(reviewer_result)
    if review_trace_summary:
        sections.append(f"# review_trace\n{review_trace_summary}")

    sections.append(f"# constraints\n{new_constraints}")

    if preferred_length:
        sections.append(f"# preferred_length\n{preferred_length}")

    sections.append(f"# output_target\n{new_output_target}")
    return "\n\n".join(sections) + "\n"


def format_review_trace_summary(reviewer_result: dict) -> str:
    trace = reviewer_result.get("review_trace", {}) if isinstance(reviewer_result, dict) else {}
    if not isinstance(trace, dict) or not trace:
        return ""

    provider = str(trace.get("provider") or "unknown").strip()
    mode = str(trace.get("mode") or "unknown").strip()
    low_confidence = "yes" if bool(trace.get("low_confidence")) else "no"
    deterministic_fallback = "yes" if bool(trace.get("deterministic_fallback_used")) else "no"
    json_refinement = "yes" if bool(trace.get("json_refinement_attempted")) else "no"
    repeated_fragments = int(trace.get("repeated_fragments", 0) or 0)

    lines = [
        f"- provider: {provider}",
        f"- mode: {mode}",
        f"- low_confidence: {low_confidence}",
        f"- deterministic_fallback: {deterministic_fallback}",
        f"- json_refinement_attempted: {json_refinement}",
        f"- repeated_fragments: {repeated_fragments}",
    ]
    return "\n".join(lines)


def build_latest_run_summary(
    *,
    task_id: str,
    draft_file: str | None,
    writer_trace: dict | None,
    reviewer_result: dict | None,
    created: dict[str, str] | None,
    loop_round: int,
    review_status: str,
) -> str:
    created = created or {}
    reviewer_result = reviewer_result or {}
    writer_trace = writer_trace or {}
    summary = str(reviewer_result.get("summary") or "").strip() or "无"
    verdict = str(reviewer_result.get("verdict") or review_status or "unknown").strip() or "unknown"
    review_trace_summary = format_review_trace_summary(reviewer_result)

    lines = [
        "# Latest Run Summary",
        "",
        "## 本轮概况",
        f"- loop_round: {loop_round}",
        f"- task_id: {task_id}",
        f"- review_status: {review_status}",
        f"- reviewer_verdict: {verdict}",
        f"- draft_file: {draft_file or '[无]'}",
        f"- reviewer_summary: {summary}",
        "",
    ]

    if review_trace_summary:
        lines.extend([
            "## Reviewer Trace",
            *review_trace_summary.splitlines(),
            "",
        ])

    if isinstance(writer_trace, dict) and writer_trace:
        fallback_lines = [f"- {item}" for item in writer_trace.get("fallbacks_used", []) if str(item).strip()]
        initial_error_lines = [f"- {item}" for item in writer_trace.get("initial_validation_errors", []) if str(item).strip()]
        final_error_lines = [f"- {item}" for item in writer_trace.get("final_validation_errors", []) if str(item).strip()]
        lines.extend([
            "## Writer Trace",
            f"- provider: {str(writer_trace.get('provider') or 'unknown').strip() or 'unknown'}",
            f"- mode: {str(writer_trace.get('mode') or 'unknown').strip() or 'unknown'}",
        ])
        if fallback_lines:
            lines.extend(["- fallbacks_used:"] + fallback_lines)
        else:
            lines.append("- fallbacks_used: none")
        if initial_error_lines:
            lines.extend(["- initial_validation_errors:"] + initial_error_lines)
        else:
            lines.append("- initial_validation_errors: none")
        if final_error_lines:
            lines.extend(["- final_validation_errors:"] + final_error_lines)
        else:
            lines.append("- final_validation_errors: none")
        lines.append("")

    artifact_lines: list[str] = []
    for key in [
        "task_file",
        "locked_file",
        "next_scene_task_file",
        "next_scene_plan_file",
        "manual_intervention_file",
        "supervisor_decision_file",
        "supervisor_rescue_draft_file",
        "supervisor_rescue_record_file",
        "lock_gate_report_file",
    ]:
        value = str(created.get(key) or "").strip()
        if value:
            artifact_lines.append(f"- {key}: {value}")

    if artifact_lines:
        lines.extend([
            "## 输出产物",
            *artifact_lines,
            "",
        ])

    major_issues = [str(item).strip() for item in reviewer_result.get("major_issues", []) if str(item).strip()]
    minor_issues = [str(item).strip() for item in reviewer_result.get("minor_issues", []) if str(item).strip()]
    if major_issues:
        lines.extend([
            "## 主要问题",
            *[f"- {item}" for item in major_issues[:5]],
            "",
        ])
    if minor_issues:
        lines.extend([
            "## 次要问题",
            *[f"- {item}" for item in minor_issues[:5]],
            "",
        ])

    next_step = "查看 reviewer 结果并决定下一步。"
    if "locked_file" in created:
        next_step = "本轮已锁定，可直接查看 locked 正文或继续下一 scene。"
    elif "manual_intervention_file" in created:
        next_step = "本轮已转人工介入，请优先查看 manual_intervention 文件。"
    elif "task_file" in created:
        next_step = "本轮已生成新的 revise/rewrite 任务，可继续自动跑下一轮。"
    lines.extend([
        "## 建议下一步",
        f"- {next_step}",
    ])

    return "\n".join(lines).strip() + "\n"


def save_latest_run_summary(
    *,
    task_id: str,
    draft_file: str | None,
    writer_trace: dict | None,
    reviewer_result: dict | None,
    created: dict[str, str] | None,
    loop_round: int,
    review_status: str,
) -> str:
    rel_path = "02_working/reviews/latest_run_summary.md"
    save_text(
        rel_path,
        build_latest_run_summary(
            task_id=task_id,
            draft_file=draft_file,
            writer_trace=writer_trace,
            reviewer_result=reviewer_result,
            created=created,
            loop_round=loop_round,
            review_status=review_status,
        ),
    )
    return rel_path


def extract_scene_stem(text: str | None) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return None

    path_stem = Path(raw).stem
    for candidate in [raw, path_stem]:
        match = re.search(r"(ch\d+_scene\d+)", candidate)
        if match:
            return match.group(1)
    return None


def infer_locked_scene_stem(task_text: str, draft_file: str) -> str:
    output_target = extract_markdown_field(task_text, "output_target")
    task_id = extract_markdown_field(task_text, "task_id")

    for candidate in [output_target, task_id, draft_file]:
        scene_stem = extract_scene_stem(candidate)
        if scene_stem:
            return scene_stem

    path = Path(draft_file)
    stem = path.stem
    stem = re.sub(r"(?:_v\d+)+$", "", stem)
    stem = re.sub(r"_rewrite\d*$", "", stem)
    return stem


def build_locked_chapter_file(task_text: str, draft_file: str, locked_dir: str) -> str:
    path = Path(draft_file)
    stem = infer_locked_scene_stem(task_text, draft_file)
    return f"{locked_dir}/chapters/{stem}{path.suffix}"


def extract_revision_count(task_id: str) -> int:
    match = re.search(r"-(?:R|RW)(\d+)$", task_id)
    if not match:
        return 0
    return int(match.group(1))


def extract_supervisor_round(task_text: str) -> int:
    raw = extract_markdown_field(task_text, "supervisor_round")
    if not raw:
        return 0
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return 0
    return max(value, 0)


def get_max_supervisor_rounds(config: dict) -> int:
    value = config.get("generation", {}).get("max_supervisor_rounds", 3)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 3
    return max(parsed, 0)


def has_supervisor_retry_budget(config: dict, task_text: str) -> bool:
    return extract_supervisor_round(task_text) < get_max_supervisor_rounds(config)


def get_effective_manual_intervention_threshold(config: dict, max_revisions: int) -> int:
    generation = config.get("generation", {})
    explicit = generation.get("local_manual_intervention_after")
    if explicit is not None:
        try:
            return max(1, int(explicit))
        except (TypeError, ValueError):
            pass

    if is_local_reviewer_mode(config) or is_local_writer_mode(config):
        return max(1, min(max_revisions, 3))
    return max(1, max_revisions)


def should_force_supervisor_takeover(config: dict, task_text: str, reviewer_result: dict) -> bool:
    if not is_supervisor_enabled(config):
        return False
    if not has_supervisor_retry_budget(config, task_text):
        return False
    if not (is_local_reviewer_mode(config) or is_local_writer_mode(config)):
        return False
    if str(reviewer_result.get("verdict") or "").strip() == "lock":
        return False

    task_id = extract_markdown_field(task_text, "task_id") or str(reviewer_result.get("task_id") or "").strip()
    revision_count = extract_revision_count(task_id)
    major_issues = [str(item).strip() for item in reviewer_result.get("major_issues", []) if str(item).strip()]
    local_reviewer_noise = any("无效英文分析" in item for item in reviewer_result.get("minor_issues", []))
    repetitive_loop = revision_count >= 2

    if local_reviewer_noise:
        return True
    if repetitive_loop and major_issues:
        return True
    return False


def build_supervisor_rescue_record_path(task_id: str) -> str:
    return f"02_working/reviews/{task_id}_supervisor_rescue.json"


def has_supervisor_rescue_record(task_id: str) -> bool:
    normalized = str(task_id or "").strip()
    if not normalized:
        return False
    return (ROOT / build_supervisor_rescue_record_path(normalized)).exists()


def is_safe_auto_lock_reason(reason: str, reviewer_result: dict) -> bool:
    normalized_reason = str(reason or "").strip()
    if not normalized_reason:
        return False

    allowed_markers = [
        "未继续给出可执行修订任务",
        "无可执行修订任务",
        "无法提出可执行",
        "没有可执行修订任务",
        "无需继续修订",
        "修订阈值",
        "建议人工介入",
        "重复问题未收敛",
        "本地 reviewer",
        "低置信度",
    ]
    if not any(marker in normalized_reason for marker in allowed_markers):
        return False

    major_issues = [str(item).strip() for item in reviewer_result.get("major_issues", []) if str(item).strip()]
    disallowed_major = [
        item
        for item in major_issues
        if all(
            marker not in item
            for marker in [
                "人工介入",
                "修订阈值",
                "无可执行修订任务",
                "未继续给出可执行修订任务",
                "无法提出可执行",
                "无需继续修订",
            ]
        )
    ]
    return not disallowed_major


def should_auto_lock_after_supervisor_rescue(config: dict, task_text: str, reviewer_result: dict) -> bool:
    if not is_supervisor_enabled(config):
        return False

    task_id = extract_markdown_field(task_text, "task_id") or str(reviewer_result.get("task_id") or "").strip()
    if not task_id or not has_supervisor_rescue_record(task_id):
        return False

    if extract_supervisor_round(task_text) <= 0:
        return False

    if str(reviewer_result.get("verdict") or "").strip() == "lock":
        return False

    reason = str(reviewer_result.get("force_manual_intervention_reason") or "").strip()
    if not is_safe_auto_lock_reason(reason, reviewer_result):
        if not (
            (is_local_reviewer_mode(config) or is_local_writer_mode(config))
            and extract_revision_count(task_id) >= 2
        ):
            return False

    return True


def build_supervisor_auto_lock_result(reviewer_result: dict, trigger_reason: str) -> dict:
    updated = dict(reviewer_result)
    summary = str(updated.get("summary") or "").strip()
    reason = str(trigger_reason or "").strip()
    decision_reason = "supervisor 已完成救场，本轮 reviewer 未继续给出可执行修订任务，按自动接管策略转入锁定。"
    if reason:
        decision_reason = f"{decision_reason} 原因：{reason}"
    elif summary:
        decision_reason = f"{decision_reason} 原始摘要：{summary}"

    updated["verdict"] = "lock"
    updated["task_goal_fulfilled"] = True
    updated["recommended_next_step"] = "lock_scene"
    updated["summary"] = decision_reason
    updated.pop("force_manual_intervention_reason", None)

    major_issues = [str(item).strip() for item in updated.get("major_issues", []) if str(item).strip()]
    filtered_major_issues = [
        item
        for item in major_issues
        if item != reason and "建议人工介入" not in item and "人工介入" not in item and "修订阈值" not in item
    ]
    updated["major_issues"] = filtered_major_issues
    return updated


def build_locked_notes_content(task_text: str, reviewer_result: dict, draft_file: str, locked_file: str) -> str:
    task_id = extract_markdown_field(task_text, "task_id") or "today"
    lock_date = task_id[:10] if re.match(r"\d{4}-\d{2}-\d{2}", task_id[:10]) else "today"
    goal = extract_markdown_field(task_text, "goal") or "本场景功能待补充"
    minor_issues = normalize_issue_lines(list(reviewer_result.get("minor_issues", [])))
    stem = Path(locked_file).stem

    lines = [
        f"# {stem} 锁定说明",
        "",
        f"- 锁定日期：{lock_date}",
        f"- 正文文件：{locked_file}",
        f"- 来源草稿：{draft_file}",
        f"- reviewer verdict：{reviewer_result.get('verdict', 'lock')}",
        f"- reviewer summary：{str(reviewer_result.get('summary', '')).strip()}",
        "",
        "## 本场景功能",
        f"- {goal}",
    ]

    if minor_issues:
        lines.extend(["", "## 后续留意"])
        lines.extend([f"- {item}" for item in minor_issues])

    return "\n".join(lines).strip() + "\n"


def build_working_notes_proposal_content(task_text: str, reviewer_result: dict, draft_file: str, locked_file: str, notes_file: str) -> str:
    goal = extract_markdown_field(task_text, "goal") or "本场景功能待补充"
    minor_issues = normalize_issue_lines(list(reviewer_result.get("minor_issues", [])))
    lines = [
        f"# {Path(locked_file).stem} canon notes 更新提议",
        "",
        f"- 建议同步到：{notes_file}",
        f"- 对应 locked 正文：{locked_file}",
        f"- 来源草稿：{draft_file}",
        f"- reviewer summary：{str(reviewer_result.get('summary', '')).strip()}",
        "",
        "## 建议保留的场景功能",
        f"- {goal}",
    ]

    if minor_issues:
        lines.extend(["", "## 可写入 notes 的后续留意"])
        lines.extend([f"- {item}" for item in minor_issues])

    return "\n".join(lines).strip() + "\n"


def build_working_state_proposal_content(task_text: str, reviewer_result: dict, locked_file: str, chapter_state_path: str | None) -> str:
    goal = extract_markdown_field(task_text, "goal") or "本场景功能待补充"
    summary = str(reviewer_result.get("summary", "")).strip()
    stem = Path(locked_file).stem
    lines = [
        f"# {stem} 对 ch01_state 的更新提议",
        "",
        f"- 建议同步到：{chapter_state_path or '03_locked/canon/ch01_state.md'}",
        f"- 对应 locked 正文：{locked_file}",
        "",
        "## 建议补入“已锁定场景”",
        f"- {stem}：{goal}",
        "",
        "## 建议补入“当前主角状态 / 已锁定线索”",
        f"- {summary or '本场景已完成锁定，可根据正文补充主角状态与线索推进。'}",
        "",
        "## 建议人工确认",
        "- 是否需要把本场新增的动作偏移写入主角状态",
        "- 是否需要把本场确认的低烈度推进写入章节节奏判断",
    ]
    return "\n".join(lines).strip() + "\n"


def build_manual_intervention_content(task_text: str, reviewer_result: dict, draft_file: str, max_revisions: int, trigger_reason: str | None = None) -> str:
    task_id = extract_markdown_field(task_text, "task_id") or "unknown-task"
    summary = str(reviewer_result.get("summary", "")).strip()
    major_issues = normalize_issue_lines(list(reviewer_result.get("major_issues", [])))
    minor_issues = normalize_issue_lines(list(reviewer_result.get("minor_issues", [])))
    review_result_path = build_review_result_path(task_id)
    repair_plan_path = build_repair_plan_path(task_id)
    lineage_path = build_revision_lineage_path(task_id)
    structured_review = None
    repair_plan = None
    lineage = None

    try:
        structured_review = load_structured_review_result(ROOT, task_id)
    except Exception:
        structured_review = None
    try:
        repair_plan = load_repair_plan(ROOT, task_id)
    except Exception:
        repair_plan = None
    try:
        lineage = load_revision_lineage(ROOT, task_id, max_revisions)
    except Exception:
        lineage = None

    unresolved_issue_lines: list[str] = []
    if structured_review is not None and structured_review.issues:
        for issue in structured_review.issues[:5]:
            unresolved_issue_lines.append(
                f"- `{issue.id}` `{issue.type.value}` `{issue.severity.value}` `{issue.target}`：{issue.message}"
            )
    else:
        unresolved_issue_lines.extend([f"- {item}" for item in major_issues[:5]])

    likely_root_causes: list[str] = []
    if trigger_reason:
        likely_root_causes.append(trigger_reason)
    if lineage is not None and lineage.escalation_reason and lineage.escalation_reason not in likely_root_causes:
        likely_root_causes.append(lineage.escalation_reason)
    if repair_plan is not None:
        likely_root_causes.append(f"当前 repair_mode 为 `{repair_plan.mode.value}`，说明问题规模已超出纯局部润色。")
    if not likely_root_causes and summary:
        likely_root_causes.append(summary)

    manual_choices = [
        "保留当前 draft 骨架，只按 `repair_plan` 修补列出的动作点。" if repair_plan and repair_plan.mode.value == RepairMode.local_fix.value else "先判断是否保留当前 draft 骨架，再决定局部改或整场重写。",
        "直接人工改当前 draft，然后重新运行 reviewer。",
        "如果当前 draft 方向已错位，放弃 auto revise，手动重写后再进审稿。",
    ]
    if lineage is not None and lineage.recurring_issue_types:
        manual_choices.append(f"优先处理重复未收敛的问题类型：{', '.join(lineage.recurring_issue_types)}。")

    inspect_files = [
        f"- 当前草稿：`{draft_file}`",
        f"- 原任务：`01_inputs/tasks/current_task.md`",
        f"- reviewer 原结果：`02_working/reviews/{task_id}_reviewer.json`",
        f"- 结构化 review：`{review_result_path}`",
        f"- repair plan：`{repair_plan_path}`",
        f"- revision lineage：`{lineage_path}`",
    ]
    based_on_path = extract_markdown_field(task_text, "based_on")
    chapter_state_path = extract_markdown_field(task_text, "chapter_state")
    review_trace_summary = format_review_trace_summary(reviewer_result)
    if based_on_path:
        inspect_files.append(f"- 前文基准：`{based_on_path}`")
    if chapter_state_path:
        inspect_files.append(f"- chapter state：`{chapter_state_path}`")

    retry_prompt_lines = [
        "请基于当前草稿执行一次人工定向修订，而不是自由重写。",
        f"目标文件：`{draft_file}`。",
    ]
    if repair_plan is not None and repair_plan.actions:
        retry_prompt_lines.append(f"修订模式：`{repair_plan.mode.value}`。")
        retry_prompt_lines.append("必须优先解决以下问题：")
        retry_prompt_lines.extend([f"- {action.issue_id} {action.instruction}" for action in repair_plan.actions[:5]])
    elif unresolved_issue_lines:
        retry_prompt_lines.append("必须优先解决以下未收敛问题：")
        retry_prompt_lines.extend(unresolved_issue_lines[:5])
    retry_prompt_lines.append("不要新增人物、设定或主线扩写；修完后再重新进入 reviewer。")

    current_status_lines = [
        f"- 当前任务：`{task_id}`",
        f"- 当前草稿：`{draft_file}`",
        f"- 当前结论：`{reviewer_result.get('verdict', 'revise')}`",
        f"- 当前摘要：{summary or '无'}",
        f"- 自动修订上限：{max_revisions}",
    ]
    if lineage is not None and lineage.revisions:
        current_status_lines.append(f"- 已记录修订轮次：{len(lineage.revisions)}")
        if lineage.recurring_issue_types:
            current_status_lines.append(f"- 重复问题类型：{', '.join(lineage.recurring_issue_types)}")
    if review_trace_summary:
        current_status_lines.append("- review trace：")
        current_status_lines.extend(review_trace_summary.splitlines())

    stop_reason_lines = [
        f"- {trigger_reason}" if trigger_reason else f"- 已达到最大自动修订次数：{max_revisions}",
    ]
    if lineage is not None and lineage.escalation_reason and lineage.escalation_reason != trigger_reason:
        stop_reason_lines.append(f"- {lineage.escalation_reason}")

    lines = [
        f"# {task_id} 人工介入说明",
        "",
        "## 当前状态",
        *current_status_lines,
        "",
        "## 为什么自动化停止",
        *stop_reason_lines,
        "",
        "## 当前未解决的关键问题",
        *(unresolved_issue_lines or ["- 暂无结构化 issue，需人工直接检查草稿与 reviewer 原文。"]),
        "",
        "## 可能根因",
        *[f"- {item}" for item in likely_root_causes],
        "",
        "## 推荐的人工处理选项",
        *[f"- {item}" for item in manual_choices],
        "",
        "## 建议优先查看的文件",
        *inspect_files,
        "",
    ]

    if review_trace_summary:
        lines.extend([
            "## 本轮 reviewer trace",
            *review_trace_summary.splitlines(),
            "",
        ])

    lines.extend([
        "## 下一次重试可直接使用的提示词",
        *[f"- {item}" for item in retry_prompt_lines],
    ])

    if minor_issues:
        lines.extend(["", "## 次要问题"])
        lines.extend([f"- {item}" for item in minor_issues[:5]])

    return "\n".join(lines).strip() + "\n"


def maybe_supervise_manual_decision(
    config: dict,
    task_text: str,
    reviewer_result: dict,
    draft_file: str,
    max_revisions: int,
    trigger_reason: str,
) -> tuple[dict | None, str | None, str | None]:
    if not is_supervisor_enabled(config):
        return None, None, None

    current_supervisor_round = extract_supervisor_round(task_text)
    max_supervisor_rounds = get_max_supervisor_rounds(config)

    decision = run_supervisor_decision(
        ROOT,
        config,
        task_text,
        reviewer_result,
        draft_file,
        max_revisions,
        trigger_reason,
        supervisor_round=current_supervisor_round,
        max_supervisor_rounds=max_supervisor_rounds,
    )

    if decision.get("action") == "manual_intervention" and current_supervisor_round < max_supervisor_rounds:
        recovery_reason = (
            f"{trigger_reason} supervisor 首轮判断倾向人工介入，但系统仍允许继续自动化。"
            "请优先给出一份可执行、可收敛的 next_task；除非完全无法提出任务，否则不要再次选择 manual_intervention。"
        )
        recovery_decision = run_supervisor_decision(
            ROOT,
            config,
            task_text,
            reviewer_result,
            draft_file,
            max_revisions,
            recovery_reason,
            supervisor_round=current_supervisor_round,
            max_supervisor_rounds=max_supervisor_rounds,
            force_continue_preference=True,
        )
        if recovery_decision.get("action") in {"continue_revise", "continue_rewrite"}:
            decision = recovery_decision

    decision_path = save_supervisor_decision(ROOT, decision)
    supervised_result = apply_supervisor_decision_to_reviewer_result(reviewer_result, decision)
    repair_plan_path = build_repair_plan_path(reviewer_result.get("task_id", "generated-task"))
    task_content = build_task_content_from_supervisor_decision(
        decision,
        task_text,
        draft_file,
        repair_plan_path=repair_plan_path,
        preferred_length_override=preferred_length_override(config),
    )
    if supervised_result.get("force_manual_intervention_reason"):
        return None, decision_path, None
    return supervised_result, decision_path, task_content


def maybe_generate_next_scene_task_draft(
    config: dict,
    task_text: str,
    locked_file: str,
    reviewer_result: dict,
) -> tuple[str | None, str | None]:
    if should_rollover_after_lock(config, locked_file):
        current_chapter = extract_chapter_number(locked_file)
        if current_chapter is None:
            return None, None
        next_chapter = current_chapter + 1
        next_task_id, task_content = build_chapter_opening_task(
            ROOT,
            config,
            chapter_number=next_chapter,
            scene_number=1,
            previous_locked_file=locked_file,
        )
        task_file = f"01_inputs/tasks/generated/{next_task_id}.md"
        save_text(task_file, task_content)
        return task_file, None

    if not is_supervisor_enabled(config):
        return None, None

    plan = run_supervisor_next_scene_task(
        ROOT,
        config,
        task_text,
        locked_file,
        reviewer_result,
    )
    if not plan:
        return None, None

    plan_path = save_next_scene_task_plan(ROOT, plan)
    task_content = build_next_scene_task_content(
        plan,
        task_text,
        locked_file,
        preferred_length_override=preferred_length_override(config),
    )
    task_file = f"01_inputs/tasks/generated/{plan['task_id']}.md"
    save_text(task_file, task_content)
    return task_file, plan_path


def maybe_prepare_supervisor_rescue_draft(
    config: dict,
    next_task_text: str,
    source_draft_file: str,
    reviewer_result: dict,
) -> tuple[str | None, str | None]:
    if not is_supervisor_enabled(config) or not is_supervisor_rescue_draft_enabled(config):
        return None, None

    output_target = extract_markdown_field(next_task_text, "output_target")
    task_id = extract_markdown_field(next_task_text, "task_id") or reviewer_result.get("task_id") or "generated-task"
    if not output_target:
        return None, None

    rescue_result = run_supervisor_rescue_draft(
        ROOT,
        config,
        next_task_text,
        source_draft_file,
        reviewer_result,
    )
    if not rescue_result:
        return None, None

    record_path = save_supervisor_rescue_record(ROOT, rescue_result)
    draft_text = str(rescue_result.get("draft_text") or "").strip()
    if not draft_text:
        return None, record_path

    cleaned_draft = clean_model_output(draft_text)
    errors = build_validation_errors(next_task_text, cleaned_draft)
    if is_scene10_like_task(next_task_text):
        errors.extend(detect_scene10_old_pattern_reuse(cleaned_draft))
    if errors:
        save_failed_draft(str(task_id), cleaned_draft, "supervisor_rescue_failed")
        save_failure_reason(str(task_id), "；".join(errors), "supervisor_rescue_failed_reason")
        return None, record_path

    save_text(output_target, cleaned_draft)
    return output_target, record_path


def route_review_result(config: dict, task_text: str, draft_file: str, reviewer_result: dict) -> dict:
    locked_dir = config["paths"].get("locked_dir", "03_locked")
    working_dir = config["paths"].get("working_dir", "02_working")
    max_revisions = int(config.get("generation", {}).get("max_auto_revisions", 5))
    verdict = reviewer_result.get("verdict")
    created: dict[str, str] = {}

    if should_auto_lock_after_supervisor_rescue(config, task_text, reviewer_result):
        auto_lock_result = build_supervisor_auto_lock_result(
            reviewer_result,
            str(reviewer_result.get("force_manual_intervention_reason") or "").strip(),
        )
        reviewer_result, lock_gate_report = apply_lock_gate(task_text, auto_lock_result, max_revisions)
        created["lock_gate_report_file"] = save_lock_gate_report(ROOT, lock_gate_report)
        if str(reviewer_result.get("verdict") or "").strip() != "lock":
            reviewer_result = dict(auto_lock_result)
            reviewer_result["summary"] = (
                f"{auto_lock_result.get('summary', '')} "
                "lock gate 已记录当前报告，但本轮按 supervisor-rescue 自动接管策略继续锁定。"
            ).strip()
        save_structured_review_result(ROOT, reviewer_result)
        save_repair_plan(ROOT, build_structured_review_result(reviewer_result))
        verdict = reviewer_result.get("verdict")

    if verdict == "lock":
        draft_content = read_text(draft_file)
        filename = Path(draft_file).name
        locked_file = build_locked_chapter_file(task_text, draft_file, locked_dir)
        candidate_file = f"{locked_dir}/candidates/{filename}"
        notes_file = f"{locked_dir}/canon/{Path(locked_file).stem}_notes.md"
        chapter_state_path = extract_markdown_field(task_text, "chapter_state")
        notes_proposal_file = f"{working_dir}/canon_updates/{Path(locked_file).stem}_notes_proposal.md"
        state_proposal_file = f"{working_dir}/canon_updates/{Path(locked_file).stem}_state_proposal.md"

        if (ROOT / locked_file).exists():
            print(f"警告：正在覆盖已有 locked 文件: {locked_file}")

        save_text(locked_file, draft_content)
        save_text(candidate_file, draft_content)
        save_text(notes_file, build_locked_notes_content(task_text, reviewer_result, draft_file, locked_file))
        save_text(
            notes_proposal_file,
            build_working_notes_proposal_content(task_text, reviewer_result, draft_file, locked_file, notes_file),
        )
        save_text(
            state_proposal_file,
            build_working_state_proposal_content(task_text, reviewer_result, locked_file, chapter_state_path),
        )
        story_state_outputs = update_story_state_on_lock(
            ROOT,
            task_text,
            locked_file,
            chapter_state_path=chapter_state_path,
        )
        tracker_outputs = update_trackers_on_lock(
            ROOT,
            task_text,
            locked_file,
            reviewer_result,
        )
        created["locked_file"] = locked_file
        created["candidate_file"] = candidate_file
        created["notes_file"] = notes_file
        created["notes_proposal_file"] = notes_proposal_file
        created["state_proposal_file"] = state_proposal_file
        created.update(story_state_outputs)
        created.update(tracker_outputs)
        next_scene_task_file, next_scene_plan_file = maybe_generate_next_scene_task_draft(
            config,
            task_text,
            locked_file,
            reviewer_result,
        )
        if next_scene_task_file:
            created["next_scene_task_file"] = next_scene_task_file
        if next_scene_plan_file:
            created["next_scene_plan_file"] = next_scene_plan_file
        return created

    mode = "revise" if verdict == "revise" else "rewrite"
    generated_dir = f"{config['paths'].get('inputs_dir', '01_inputs')}/tasks/generated"
    task_id = extract_markdown_field(task_text, "task_id") or "generated-task"
    forced_manual_reason = str(reviewer_result.get("force_manual_intervention_reason", "")).strip()

    if not forced_manual_reason and should_force_supervisor_takeover(config, task_text, reviewer_result):
        forced_manual_reason = "本地 reviewer / writer 连续多轮未稳定收敛，提前交由 supervisor 接管。"
        reviewer_result["force_manual_intervention_reason"] = forced_manual_reason
        summary = str(reviewer_result.get("summary") or "").strip()
        if forced_manual_reason not in summary:
            reviewer_result["summary"] = f"{forced_manual_reason} {summary}".strip()
        major_issues = [str(item).strip() for item in reviewer_result.get("major_issues", []) if str(item).strip()]
        if forced_manual_reason not in major_issues:
            reviewer_result["major_issues"] = [forced_manual_reason] + major_issues

    if forced_manual_reason:
        supervised_result = None
        supervisor_decision_path = None
        supervisor_task_content = None
        if has_supervisor_retry_budget(config, task_text):
            supervised_result, supervisor_decision_path, supervisor_task_content = maybe_supervise_manual_decision(
                config,
                task_text,
                reviewer_result,
                draft_file,
                max_revisions,
                forced_manual_reason,
            )
        if supervisor_decision_path:
            created["supervisor_decision_file"] = supervisor_decision_path
        if supervised_result is not None:
            mode = "revise" if supervised_result.get("verdict") == "revise" else "rewrite"
            suffix = "revision_auto" if mode == "revise" else "rewrite_auto"
            task_file = f"{generated_dir}/{task_id}_{suffix}.md"
            task_content = supervisor_task_content or build_generated_task_content(task_text, supervised_result, draft_file, mode, config=config)
            save_text(task_file, task_content)
            created["task_file"] = task_file
            rescue_draft_file, rescue_record_file = maybe_prepare_supervisor_rescue_draft(
                config,
                task_content,
                draft_file,
                supervised_result,
            )
            if rescue_draft_file:
                created["supervisor_rescue_draft_file"] = rescue_draft_file
            if rescue_record_file:
                created["supervisor_rescue_record_file"] = rescue_record_file
            return created

        manual_intervention_file = f"{working_dir}/reviews/{task_id}_manual_intervention.md"
        if not has_supervisor_retry_budget(config, task_text):
            forced_manual_reason = f"{forced_manual_reason} supervisor 接管轮次已用尽。"
        save_text(
            manual_intervention_file,
            build_manual_intervention_content(task_text, reviewer_result, draft_file, max_revisions, trigger_reason=forced_manual_reason),
        )
        update_structured_review_status(
            ROOT,
            task_id,
            ReviewStatus.manual_intervention,
            forced_manual_reason,
        )
        created["manual_intervention_file"] = manual_intervention_file
        return created

    if mode in {"revise", "rewrite"} and extract_revision_count(task_id) >= max_revisions:
        max_revision_reason = f"{str(reviewer_result.get('summary', '')).strip()} 已达到最大自动修订次数，转人工介入。"
        supervised_result = None
        supervisor_decision_path = None
        supervisor_task_content = None
        if has_supervisor_retry_budget(config, task_text):
            supervised_result, supervisor_decision_path, supervisor_task_content = maybe_supervise_manual_decision(
                config,
                task_text,
                reviewer_result,
                draft_file,
                max_revisions,
                max_revision_reason,
            )
        if supervisor_decision_path:
            created["supervisor_decision_file"] = supervisor_decision_path
        if supervised_result is not None:
            mode = "revise" if supervised_result.get("verdict") == "revise" else "rewrite"
            suffix = "revision_auto" if mode == "revise" else "rewrite_auto"
            task_file = f"{generated_dir}/{task_id}_{suffix}.md"
            task_content = supervisor_task_content or build_generated_task_content(task_text, supervised_result, draft_file, mode, config=config)
            save_text(task_file, task_content)
            created["task_file"] = task_file
            rescue_draft_file, rescue_record_file = maybe_prepare_supervisor_rescue_draft(
                config,
                task_content,
                draft_file,
                supervised_result,
            )
            if rescue_draft_file:
                created["supervisor_rescue_draft_file"] = rescue_draft_file
            if rescue_record_file:
                created["supervisor_rescue_record_file"] = rescue_record_file
            return created

        manual_intervention_file = f"{working_dir}/reviews/{task_id}_manual_intervention.md"
        if not has_supervisor_retry_budget(config, task_text):
            max_revision_reason = f"{max_revision_reason} supervisor 接管轮次已用尽。"
        save_text(
            manual_intervention_file,
            build_manual_intervention_content(task_text, reviewer_result, draft_file, max_revisions, trigger_reason=max_revision_reason),
        )
        update_structured_review_status(
            ROOT,
            task_id,
            ReviewStatus.manual_intervention,
            max_revision_reason,
        )
        created["manual_intervention_file"] = manual_intervention_file
        return created

    suffix = "revision_auto" if mode == "revise" else "rewrite_auto"
    task_file = f"{generated_dir}/{task_id}_{suffix}.md"
    task_content = build_generated_task_content(task_text, reviewer_result, draft_file, mode, config=config)
    save_text(task_file, task_content)
    created["task_file"] = task_file
    return created


def set_current_task_from_file(task_file: str) -> str:
    task_content = read_text(task_file)
    save_text("01_inputs/tasks/current_task.md", task_content)
    return extract_markdown_field(task_content, "task_id") or task_file

def main() -> None:
    try:
        config = load_runtime_config(ROOT)
        validate_local_model_endpoints(config)
        max_revisions = int(config.get("generation", {}).get("max_auto_revisions", 5))
        manual_intervention_after = get_effective_manual_intervention_threshold(config, max_revisions)
        loop_round = 1
        restarted_task_id = prepare_runtime_start(config)
        if restarted_task_id:
            print(f"运行模式：restart，已重置当前任务到 {restarted_task_id}")
        else:
            print(f"运行模式：{get_run_mode(config)}")

        while True:
            current_task_text = read_text("01_inputs/tasks/current_task.md")
            current_task_id = extract_markdown_field(current_task_text, "task_id") or "unknown-task"
            print(f"自动流程第 {loop_round} 轮：当前任务 {current_task_id}")

            draft_result = None if should_skip_existing_draft_reuse(config, loop_round) else build_existing_draft_result(current_task_text)
            if draft_result:
                print(f"检测到已有草稿待审，直接复用: {draft_result['draft_file']}")
            else:
                print("步骤 1/3：正在整理当前上下文...")
                current_context = compile_context(config)
                print(f"已生成上下文文件: {config['output']['context_file']}")

                print("步骤 2/3：正在生成草稿...")
                try:
                    draft_result = write_draft(config, current_context)
                except Exception as error:
                    if extract_revision_count(current_task_id) >= max_revisions:
                        output_target = extract_markdown_field(current_task_text, "output_target") or "[未生成草稿]"
                        manual_intervention_file = f"02_working/reviews/{current_task_id}_manual_intervention.md"
                        save_text(
                            manual_intervention_file,
                            build_manual_intervention_content(
                                current_task_text,
                                {
                                    "verdict": "revise",
                                    "summary": f"写稿阶段失败：{error}",
                                    "major_issues": [str(error)],
                                    "minor_issues": [],
                                },
                                output_target,
                                max_revisions,
                            ),
                        )
                        print(f"写稿阶段失败，且已达到最大自动修订次数（{max_revisions}次），请人工介入。")
                        print(f"已生成人工介入提醒: {manual_intervention_file}")
                        print("本次自动闭环完成。")
                        break
                    raise

            print("步骤 3/3：正在执行审稿与后续分流...")
            try:
                _, reviewer_json_path = review_scene_file(config, draft_result["draft_file"])
            except Exception as error:
                retry_needed_file = f"02_working/reviews/{current_task_id}_review_retry_needed.md"
                save_text(
                    retry_needed_file,
                    build_review_retry_needed_content(current_task_text, draft_result["draft_file"], str(error)),
                )
                print(f"审稿失败，已生成重试提醒: {retry_needed_file}")
                raise

            reviewer_result = json.loads(read_text(reviewer_json_path))
            review_trace = reviewer_result.get("review_trace", {}) if isinstance(reviewer_result, dict) else {}
            if isinstance(review_trace, dict) and review_trace:
                trace_mode = str(review_trace.get("mode") or "").strip() or "unknown"
                trace_provider = str(review_trace.get("provider") or "").strip() or "unknown"
                trace_low_confidence = bool(review_trace.get("low_confidence"))
                trace_fallback = bool(review_trace.get("deterministic_fallback_used"))
                print(
                    "review trace："
                    f"provider={trace_provider} mode={trace_mode} "
                    f"low_confidence={'yes' if trace_low_confidence else 'no'} "
                    f"deterministic_fallback={'yes' if trace_fallback else 'no'}"
                )
            structured_review = None
            try:
                structured_review = load_structured_review_result(ROOT, reviewer_result.get("task_id", current_task_id))
            except Exception:
                structured_review = None

            lock_gate_report_path = None
            if reviewer_result.get("verdict") == "lock":
                reviewer_result, lock_gate_report = apply_lock_gate(current_task_text, reviewer_result, max_revisions)
                lock_gate_report_path = save_lock_gate_report(ROOT, lock_gate_report)
                save_text(reviewer_json_path, json.dumps(reviewer_result, ensure_ascii=False, indent=2))
                save_structured_review_result(ROOT, reviewer_result)
                save_repair_plan(ROOT, build_structured_review_result(reviewer_result))
                try:
                    structured_review = load_structured_review_result(ROOT, reviewer_result.get("task_id", current_task_id))
                except Exception:
                    structured_review = None

            lineage_path = None
            if structured_review is not None:
                lineage, lineage_path = append_revision_lineage(
                    ROOT,
                    structured_review,
                    draft_result["draft_file"],
                    manual_intervention_after,
                )
                print(build_revision_lineage_summary(lineage))
                if should_trigger_manual_intervention(lineage) and reviewer_result.get("verdict") != "lock":
                    reviewer_result["force_manual_intervention_reason"] = lineage.escalation_reason
                    reviewer_result["summary"] = lineage.escalation_reason
                    major_issues = list(reviewer_result.get("major_issues", []))
                    if lineage.escalation_reason not in major_issues:
                        major_issues.insert(0, lineage.escalation_reason)
                    reviewer_result["major_issues"] = major_issues
                    save_text(reviewer_json_path, json.dumps(reviewer_result, ensure_ascii=False, indent=2))
                    save_structured_review_result(ROOT, reviewer_result)
                    save_repair_plan(ROOT, build_structured_review_result(reviewer_result))
                    try:
                        structured_review = load_structured_review_result(ROOT, reviewer_result.get("task_id", current_task_id))
                    except Exception:
                        structured_review = None

            created = route_review_result(
                config,
                draft_result["task_text"],
                draft_result["draft_file"],
                reviewer_result,
            )

            print(f"已保存 reviewer 结果: {reviewer_json_path}")
            if structured_review is not None:
                print(f"已保存结构化审稿结果: 02_working/reviews/{structured_review.task_id}_review_result.json")
                print(f"已保存 repair plan: 02_working/reviews/{structured_review.task_id}_repair_plan.json")
            if lineage_path is not None:
                print(f"已保存 revision lineage: {lineage_path}")
            if "supervisor_decision_file" in created:
                print(f"已保存 supervisor 决策: {created['supervisor_decision_file']}")
                if "supervisor_rescue_record_file" in created:
                    if "supervisor_rescue_draft_file" in created:
                        print(f"已保存 supervisor 救场记录: {created['supervisor_rescue_record_file']}")
                    else:
                        print(f"已保存 supervisor 救场记录（草稿未采用）: {created['supervisor_rescue_record_file']}")
            if "supervisor_rescue_draft_file" in created:
                print(f"已生成 supervisor 救场稿: {created['supervisor_rescue_draft_file']}")
            if lock_gate_report_path is not None:
                print(f"已保存 lock gate 报告: {lock_gate_report_path}")
                if reviewer_result.get("verdict") != "lock":
                    print("锁定闸门未通过，已阻止本次 lock 并转入修订分流。")

            created_lock_gate_report = created.get("lock_gate_report_file")
            if created_lock_gate_report and created_lock_gate_report != lock_gate_report_path:
                print(f"已保存 lock gate 报告: {created_lock_gate_report}")

            review_status = str(reviewer_result.get("verdict") or "")
            if "locked_file" in created:
                review_status = "lock"
            elif "manual_intervention_file" in created:
                review_status = "manual_intervention"
            elif not review_status and structured_review is not None:
                review_status = structured_review.status.value

            latest_run_summary_file = save_latest_run_summary(
                task_id=current_task_id,
                draft_file=draft_result.get("draft_file") if isinstance(draft_result, dict) else None,
                writer_trace=draft_result.get("writer_trace") if isinstance(draft_result, dict) else None,
                reviewer_result=reviewer_result,
                created=created,
                loop_round=loop_round,
                review_status=review_status,
            )
            print(f"已更新运行总览: {latest_run_summary_file}")
            if review_status == "lock":
                print(f"已自动锁定到 {created['locked_file']}")
                print("如需人工修订，请直接编辑 locked 文件")
                print(f"已生成候选锁定文件: {created['candidate_file']}")
                print(f"已生成锁定 notes 草稿: {created['notes_file']}")
                print(f"已生成 working notes 更新提议: {created['notes_proposal_file']}")
                print(f"已生成 working state 更新提议: {created['state_proposal_file']}")
                print(f"已更新 story state: {created['story_state_file']}")
                print(f"已生成 story state patch: {created['story_state_patch_file']}")
                print(f"已生成 story state diff: {created['story_state_diff_file']}")
                if "next_scene_plan_file" in created:
                    print(f"已生成下一 scene 规划: {created['next_scene_plan_file']}")
                if "next_scene_task_file" in created:
                    next_task_text = read_text(created["next_scene_task_file"])
                    next_chapter_number, next_scene_number = extract_task_progress(next_task_text)
                    current_chapter_number = extract_chapter_number(created["locked_file"])
                    if (
                        current_chapter_number is not None
                        and next_chapter_number is not None
                        and next_chapter_number > current_chapter_number
                        and next_scene_number == 1
                    ):
                        print(f"已生成下一章启动任务: {created['next_scene_task_file']}")
                    else:
                        print(f"已生成下一 scene 任务草案: {created['next_scene_task_file']}")
                    if should_continue_after_lock(config, created["next_scene_task_file"]):
                        next_task_id = set_current_task_from_file(created["next_scene_task_file"])
                        print(f"检测到 lock 后续任务，已自动切换到下一任务: {next_task_id}")
                        loop_round += 1
                        continue
                print("本次自动闭环完成。")
                break

            if "manual_intervention_file" in created:
                print(f"已达到最大自动修订次数（{max_revisions}次），请人工介入。")
                print(f"已生成人工介入提醒: {created['manual_intervention_file']}")
                print("本次自动闭环完成。")
                break

            if review_status in {"revise", "rewrite"} and "task_file" in created:
                next_task_id = set_current_task_from_file(created["task_file"])
                print(f"检测到 {review_status}，已自动切换到下一轮任务: {next_task_id}")
                loop_round += 1
                continue

            print(f"已生成后续任务草稿: {created['task_file']}")
            print("本次自动闭环完成。")
            break

    except FileNotFoundError as e:
        print(f"缺少输入文件: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
    except requests.exceptions.ReadTimeout:
        print("运行失败: 请求模型超时。请缩短任务输入，或提高 request_timeout。")
    except Exception as e:
        print(f"运行失败: {e}")


if __name__ == "__main__":
    main()
