import json
import re
from pathlib import Path

import requests
import yaml
from chapter_trackers import update_trackers_on_lock
from deepseek_supervisor import apply_supervisor_decision_to_reviewer_result, build_next_scene_task_content, build_task_content_from_supervisor_decision, is_supervisor_enabled, run_supervisor_decision, run_supervisor_next_scene_task, run_supervisor_rescue_draft, save_next_scene_task_plan, save_supervisor_decision, save_supervisor_rescue_record
from issue_filters import filter_shared_issues
from jsonschema import validate
from lock_gate import apply_lock_gate, save_lock_gate_report
from review_models import RepairMode, ReviewStatus, build_repair_plan_path, build_review_result_path, build_structured_review_result, load_repair_plan, load_structured_review_result, save_repair_plan, save_structured_review_result, update_structured_review_status
from review_scene import review_scene_file
from revision_lineage import append_revision_lineage, build_revision_lineage_path, build_revision_lineage_summary, load_revision_lineage, should_trigger_manual_intervention
from story_state import update_story_state_on_lock


ROOT = Path(__file__).resolve().parent.parent


def read_text(rel_path: str) -> str:
    path = ROOT / rel_path
    return path.read_text(encoding="utf-8")


def load_yaml(rel_path: str) -> dict:
    path = ROOT / rel_path
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_text(rel_path: str, content: str) -> None:
    path = ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def clip_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[已截断]"


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

def compile_context(config: dict) -> str:
    task_text = clip_text(read_text("01_inputs/tasks/current_task.md"), 1600)
    novel_manifest = clip_text(read_text("00_manifest/novel_manifest.md"), 900)
    world_bible = clip_text(read_text("00_manifest/world_bible.md"), 700)
    character_bible_full = read_text("00_manifest/character_bible.md")
    relevant_characters = build_relevant_character_section(task_text, character_bible_full)
    character_bible = clip_text(read_text("00_manifest/character_bible.md"), 700)
    life_notes = clip_text(read_text("01_inputs/life_notes/latest.md"), 800)

    based_on_path = extract_markdown_field(task_text, "based_on")
    based_on_section = ""

    if based_on_path:
        based_on_path = based_on_path.strip()
        try:
            based_on_text = clip_text(read_text(based_on_path), 1600)
            based_on_section = f"""

# 本次修订所依据的旧稿
来源文件：{based_on_path}

{based_on_text}
"""
        except FileNotFoundError:
            based_on_section = f"""

# 本次修订所依据的旧稿
来源文件：{based_on_path}

[警告：未找到该文件，无法载入旧稿内容]
"""

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

    compiled = f"""# 当前任务
{task_text}

# 本次必须遵守的项目总纲
{novel_manifest}

# 本次相关世界设定
{world_bible}

# 本次相关人物设定
{relevant_characters}

# 本次生活素材使用规则
- 生活素材只能提取气氛、感官、情绪、节奏、意象
- 禁止直接搬运现代现实世界的具体物件或设施进入小说场景
- 如与小说世界冲突，必须优先服从小说设定

# 本次可借用的生活素材
{life_notes}{based_on_section}{chapter_state_section}
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


def build_writer_repair_rules(repair_mode: str | None) -> list[str]:
    if repair_mode == RepairMode.local_fix.value:
        return [
            "本次是局部修补，不要推倒整场重写。",
            "优先保留旧稿已经可用的段落、动作顺序和场景结构。",
            "只修 repair_plan 指向的问题段落与句子。",
        ]
    if repair_mode == RepairMode.partial_redraft.value:
        return [
            "本次允许局部重写，但不要扩大成整场翻写。",
            "优先保留方向正确的场景骨架，只重写受影响的段落块。",
            "如果 repair_plan 未要求，不要更换场景地点、人物边界和核心推进方式。",
        ]
    if repair_mode == RepairMode.full_redraft.value:
        return [
            "本次允许整场重写，但仍须严格围绕 repair_plan 的核心问题。",
            "重写时优先修复核心推进失败、约束冲突或场景功能错位。",
            "即使整场重写，也不要擅自新增设定、人物或主线外扩。",
        ]
    return []


def build_writer_repair_section(task_text: str) -> str:
    repair_mode, repair_plan_path, repair_actions = load_repair_guidance(task_text)
    if not repair_mode and not repair_plan_path and not repair_actions:
        return ""

    lines = ["【修订执行计划】"]
    if repair_mode:
        lines.append(f"- repair_mode: {repair_mode}")
    if repair_plan_path:
        lines.append(f"- repair_plan: {repair_plan_path}")

    mode_rules = build_writer_repair_rules(repair_mode)
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
    avoid_motifs = extract_markdown_list_field(task_text, "avoid_motifs")

    if not any([scene_purpose, information_gain, plot_progress, decision_shift, avoid_motifs]):
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

    deduped_information_gain: list[str] = []
    for item in information_gain:
        if item not in deduped_information_gain:
            deduped_information_gain.append(item)

    deduped_avoid_motifs: list[str] = []
    for item in avoid_motifs:
        if item not in deduped_avoid_motifs:
            deduped_avoid_motifs.append(item)

    return {
        "scene_purpose": scene_purpose,
        "required_information_gain": deduped_information_gain,
        "required_plot_progress": plot_progress,
        "required_decision_shift": decision_shift,
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


def build_writer_user_prompt(task_text: str, current_context: str, decision: dict) -> str:
    repair_section = build_writer_repair_section(task_text)
    structure_section = build_writer_structure_section(task_text)
    scene10_guardrails = build_scene10_prompt_guardrails(task_text)
    repair_rules = build_writer_repair_rules(extract_markdown_field(task_text, "repair_mode"))
    repair_rule_lines = "\n".join([f"14. {item}" for item in repair_rules[:1]]) if repair_rules else ""

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
{repair_rule_lines}
【任务单】
{task_text}

【当前上下文】
{current_context}

{repair_section}

{structure_section}

{scene10_guardrails}

【决策信息】
{json.dumps(decision, ensure_ascii=False, indent=2)}
"""
    return prompt.replace("\n\n\n", "\n\n")


def generate_markdown_draft(config: dict, current_context: str, decision: dict) -> str:
    system_prompt = read_text("prompts/writer_system.md")
    task_text = read_text("01_inputs/tasks/current_task.md")
    user_prompt = build_writer_user_prompt(task_text, current_context, decision)

    print("正在请求模型生成草稿，请稍候...")
    markdown_text = call_ollama(
        model=config["writer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["writer"]["base_url"],
        num_ctx=config["generation"]["write_num_ctx"],
        temperature=config["generation"]["temperature"],
        timeout=config["generation"]["request_timeout"],
        num_predict=1000,
    )

    return markdown_text.strip()

def rewrite_script_to_prose(config: dict, current_context: str, bad_draft: str) -> str:
    system_prompt = """你是小说改写助手。
你的任务是把一段剧本体、分镜体或舞台说明式文字，改写为连续的小说正文 prose。
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

    print("检测到剧本体，正在尝试自动改写为小说正文...")
    rewritten = call_ollama(
        model=config["writer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["writer"]["base_url"],
        num_ctx=config["generation"]["write_num_ctx"],
        temperature=0.2,
        timeout=config["generation"]["request_timeout"],
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
    refined = call_ollama(
        model=config["writer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["writer"]["base_url"],
        num_ctx=config["generation"]["write_num_ctx"],
        temperature=0.1,
        timeout=config["generation"]["request_timeout"],
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
    continued = call_ollama(
        model=config["writer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["writer"]["base_url"],
        num_ctx=config["generation"]["write_num_ctx"],
        temperature=0.2,
        timeout=config["generation"]["request_timeout"],
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
    repaired = call_ollama(
        model=config["writer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["writer"]["base_url"],
        num_ctx=config["generation"]["write_num_ctx"],
        temperature=0.2,
        timeout=config["generation"]["request_timeout"],
        num_predict=1200,
    )

    return clean_model_output(repaired)

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

    raw_markdown_text = generate_markdown_draft(config, current_context, decision)
    markdown_text = clean_model_output(raw_markdown_text)

    if not markdown_text and raw_markdown_text.strip():
        save_failed_draft(task_id, raw_markdown_text, "first_failed_raw")
        rewritten = rewrite_script_to_prose(config, current_context, raw_markdown_text)
        save_failed_draft(task_id, rewritten, "rewritten_attempt")

        rewritten_errors = build_validation_errors(task_text, rewritten)
        if not rewritten_errors:
            markdown_text = rewritten
        else:
            save_failure_reason(task_id, "；".join(rewritten_errors), "rewritten_failed_reason")
            refined = extract_plain_prose(config, current_context, rewritten)
            save_failed_draft(task_id, refined, "refined_attempt")

            refined_errors = build_validation_errors(task_text, refined)
            if refined_errors:
                save_failure_reason(task_id, "；".join(refined_errors), "refined_failed_reason")
                raise ValueError(f"草稿验收失败（提纯后仍不通过）: {'；'.join(refined_errors)}")

            markdown_text = refined

    errors = build_validation_errors(task_text, markdown_text)
    errors = build_validation_errors(task_text, markdown_text)
    if errors:
        save_failed_draft(task_id, markdown_text, "first_failed")
        save_failure_reason(task_id, "；".join(errors), "first_failed_reason")

        if any("草稿疑似被截断" in e for e in errors):
            continued = continue_truncated_draft(config, current_context, raw_markdown_text)
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

        # 第一层 fallback：剧本体 -> prose 改写
        if errors and any("剧本体" in e or "分镜体" in e for e in errors):
            rewritten = rewrite_script_to_prose(config, current_context, markdown_text)
            save_failed_draft(task_id, rewritten, "rewritten_attempt")

            rewritten_errors = build_validation_errors(task_text, rewritten)
            if not rewritten_errors:
                markdown_text = rewritten
            else:
                save_failure_reason(task_id, "；".join(rewritten_errors), "rewritten_failed_reason")

                # 第二层 fallback：提纯正文
                refined = extract_plain_prose(config, current_context, rewritten)
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
            save_failed_draft(task_id, repaired, "repaired_attempt")
            repaired_errors = build_validation_errors(task_text, repaired)
            if repaired_errors:
                save_failure_reason(task_id, "；".join(repaired_errors), "repaired_failed_reason")
                raise ValueError(f"草稿验收失败: {'；'.join(repaired_errors)}")
            markdown_text = repaired

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
    }


def build_existing_draft_result(task_text: str) -> dict | None:
    task_id = extract_markdown_field(task_text, "task_id") or "generated-task"
    draft_file = extract_markdown_field(task_text, "output_target")
    if not draft_file:
        return None

    reviewer_json_path = f"02_working/reviews/{task_id}_reviewer.json"
    if not (ROOT / draft_file).exists():
        return None
    if (ROOT / reviewer_json_path).exists():
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


def get_auto_continue_target_scene(config: dict) -> int | None:
    generation = config.get("generation", {})
    value = generation.get("auto_continue_until_scene")
    if value in (None, "", 0):
        return None
    try:
        target = int(value)
    except (TypeError, ValueError):
        return None
    return target if target > 0 else None


def should_continue_after_lock(config: dict, next_scene_task_file: str | None) -> bool:
    if not next_scene_task_file:
        return False
    target_scene = get_auto_continue_target_scene(config)
    if target_scene is None:
        return False
    task_text = read_text(next_scene_task_file)
    output_target = extract_markdown_field(task_text, "output_target") or next_scene_task_file
    next_scene_number = extract_scene_number(output_target) or extract_scene_number(task_text)
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


def build_followup_task_id(task_id: str, mode: str) -> str:
    base = re.sub(r"-R\d+$", "", task_id)
    match = re.search(r"-R(\d+)$", task_id)
    if mode == "revise":
        if match:
            next_number = int(match.group(1)) + 1
        else:
            next_number = 1
        return f"{base}-R{next_number}"
    if mode == "rewrite":
        return f"{base}-RW1"
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


def build_followup_goal(original_goal: str, reviewer_result: dict, mode: str, task_text: str, repair_mode: str | None = None, repair_instructions: list[str] | None = None) -> str:
    base_goal = strip_revision_prefix(original_goal)
    summary = str(reviewer_result.get("summary", "")).strip()
    filtered_major, filtered_minor = get_filtered_reviewer_issues(reviewer_result, task_text)
    major_issues = filter_usable_issues(filtered_major)
    minor_issues = filter_usable_issues(filtered_minor)
    issues = filter_followup_issue_lines(
        major_issues + minor_issues
    )

    if mode == "rewrite":
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
    if issue_text:
        return f"{prefix}：{base_goal}。本次重点解决：{issue_text}"
    return f"{prefix}：{base_goal}。"


def build_followup_constraints(task_text: str, reviewer_result: dict, repair_mode: str | None = None, repair_instructions: list[str] | None = None) -> str:
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


def build_generated_task_content(task_text: str, reviewer_result: dict, draft_file: str, mode: str) -> str:
    task_id = extract_markdown_field(task_text, "task_id") or "generated-task"
    original_goal = extract_markdown_field(task_text, "goal") or "根据 reviewer 结果继续处理当前草稿"
    chapter_state = extract_markdown_field(task_text, "chapter_state")
    preferred_length = extract_markdown_field(task_text, "preferred_length")
    repair_mode = None
    repair_plan_path = None
    repair_instructions: list[str] = []

    if mode == "revise":
        task_id_for_plan = extract_markdown_field(task_text, "task_id") or "generated-task"
        repair_plan_path = build_repair_plan_path(task_id_for_plan)
        try:
            repair_plan = load_repair_plan(ROOT, task_id_for_plan)
            repair_mode = repair_plan.mode.value
            repair_instructions = [action.instruction for action in repair_plan.actions]
        except Exception:
            repair_plan_path = None

    new_task_id = build_followup_task_id(task_id, mode)
    new_goal = build_followup_goal(original_goal, reviewer_result, mode, task_text, repair_mode=repair_mode, repair_instructions=repair_instructions)
    new_constraints = build_followup_constraints(task_text, reviewer_result, repair_mode=repair_mode, repair_instructions=repair_instructions)
    new_output_target = build_followup_output_target(draft_file, mode)
    structural_fields = build_structural_task_fields(task_text, reviewer_result)
    information_gain_block = "\n".join(f"- {item}" for item in structural_fields["required_information_gain"])
    avoid_motifs_block = "\n".join(f"- {item}" for item in structural_fields["avoid_motifs"])

    sections = [
        f"# task_id\n{new_task_id}",
        f"# goal\n{new_goal}",
        f"# based_on\n{draft_file}",
        f"# scene_purpose\n{structural_fields['scene_purpose']}",
        f"# required_information_gain\n{information_gain_block}",
        f"# required_plot_progress\n{structural_fields['required_plot_progress']}",
        f"# required_decision_shift\n{structural_fields['required_decision_shift']}",
    ]

    if avoid_motifs_block:
        sections.append(f"# avoid_motifs\n{avoid_motifs_block}")

    if chapter_state:
        sections.append(f"# chapter_state\n{chapter_state}")

    if repair_mode:
        sections.append(f"# repair_mode\n{repair_mode}")

    if repair_plan_path:
        sections.append(f"# repair_plan\n{repair_plan_path}")

    sections.append(f"# constraints\n{new_constraints}")

    if preferred_length:
        sections.append(f"# preferred_length\n{preferred_length}")

    sections.append(f"# output_target\n{new_output_target}")
    return "\n\n".join(sections) + "\n"


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
    match = re.search(r"-R(\d+)$", task_id)
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


def build_supervisor_rescue_record_path(task_id: str) -> str:
    return f"02_working/reviews/{task_id}_supervisor_rescue.json"


def has_supervisor_rescue_record(task_id: str) -> bool:
    normalized = str(task_id or "").strip()
    if not normalized:
        return False
    return (ROOT / build_supervisor_rescue_record_path(normalized)).exists()


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

    return bool(str(reviewer_result.get("force_manual_intervention_reason") or "").strip())


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
        "## 下一次重试可直接使用的提示词",
        *[f"- {item}" for item in retry_prompt_lines],
    ]

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
    task_content = build_next_scene_task_content(plan, task_text, locked_file)
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
        reviewer_result = build_supervisor_auto_lock_result(
            reviewer_result,
            str(reviewer_result.get("force_manual_intervention_reason") or "").strip(),
        )
        reviewer_result, lock_gate_report = apply_lock_gate(task_text, reviewer_result, max_revisions)
        created["lock_gate_report_file"] = save_lock_gate_report(ROOT, lock_gate_report)
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
            task_content = supervisor_task_content or build_generated_task_content(task_text, supervised_result, draft_file, mode)
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

    if mode == "revise" and extract_revision_count(task_id) >= max_revisions:
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
            task_content = supervisor_task_content or build_generated_task_content(task_text, supervised_result, draft_file, mode)
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
    task_content = build_generated_task_content(task_text, reviewer_result, draft_file, mode)
    save_text(task_file, task_content)
    created["task_file"] = task_file
    return created


def set_current_task_from_file(task_file: str) -> str:
    task_content = read_text(task_file)
    save_text("01_inputs/tasks/current_task.md", task_content)
    return extract_markdown_field(task_content, "task_id") or task_file

def main() -> None:
    try:
        config = load_yaml("app/config.yaml")
        max_revisions = int(config.get("generation", {}).get("max_auto_revisions", 5))
        loop_round = 1

        while True:
            current_task_text = read_text("01_inputs/tasks/current_task.md")
            current_task_id = extract_markdown_field(current_task_text, "task_id") or "unknown-task"
            print(f"自动流程第 {loop_round} 轮：当前任务 {current_task_id}")

            draft_result = build_existing_draft_result(current_task_text)
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
                    max_revisions,
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

            if "locked_file" in created:
                review_status = "lock"
            elif "manual_intervention_file" in created:
                review_status = "manual_intervention"
            elif structured_review is not None:
                review_status = structured_review.status.value
            else:
                review_status = reviewer_result.get("verdict")
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
                    print(f"已生成下一 scene 任务草案: {created['next_scene_task_file']}")
                    if should_continue_after_lock(config, created["next_scene_task_file"]):
                        next_task_id = set_current_task_from_file(created["next_scene_task_file"])
                        print(f"检测到 lock 后续任务，已自动切换到下一 scene: {next_task_id}")
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