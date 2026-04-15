from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from project_inputs import get_list, get_section, load_human_input


ROOT = Path(__file__).resolve().parent.parent


def chapter_label(chapter_number: int) -> str:
    return f"ch{int(chapter_number):02d}"


def scene_label(chapter_number: int, scene_number: int) -> str:
    return f"{chapter_label(chapter_number)}_scene{int(scene_number):02d}"


def chapter_state_path(chapter_number: int) -> str:
    return f"03_locked/canon/{chapter_label(chapter_number)}_state.md"


def draft_output_path(chapter_number: int, scene_number: int) -> str:
    return f"02_working/drafts/{scene_label(chapter_number, scene_number)}.md"


def extract_scene_progress(path_or_text: str) -> tuple[int | None, int | None]:
    match = re.search(r"ch(\d+)_scene(\d+)", str(path_or_text))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def get_run_int(config: dict[str, Any], field: str) -> int | None:
    value = ((config.get("run") or {}).get(field))
    if value in (None, "", 0):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def get_start_progress(config: dict[str, Any]) -> tuple[int, int]:
    chapter_number = get_run_int(config, "start_chapter") or 1
    scene_number = get_run_int(config, "start_scene") or 1
    return chapter_number, scene_number


def get_max_scenes_per_chapter(config: dict[str, Any]) -> int | None:
    return get_run_int(config, "max_scenes_per_chapter")


def should_rollover_after_lock(config: dict[str, Any], locked_file: str) -> bool:
    limit = get_max_scenes_per_chapter(config)
    if limit is None:
        return False
    _, scene_number = extract_scene_progress(locked_file)
    if scene_number is None:
        return False
    return scene_number >= limit


def load_story_state(root: Path) -> dict[str, Any]:
    path = root / "03_locked/state/story_state.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def parse_volume_plan(manifest_text: str) -> list[dict[str, str]]:
    plans: list[dict[str, str]] = []
    matches = re.findall(r"####\s*第([一二三四五六七八九十0-9]+)卷[:：]\s*([^\n]+)\n- 功能[:：]\s*([^\n]+)", manifest_text)
    for _, title, function in matches:
        plans.append({"title": str(title).strip(), "function": str(function).strip()})
    return plans


def resolve_volume_context(root: Path, chapter_number: int) -> dict[str, str]:
    manifest_path = root / "00_manifest/novel_manifest.md"
    if not manifest_path.exists():
        return {}
    plans = parse_volume_plan(manifest_path.read_text(encoding="utf-8"))
    if not plans:
        return {}
    # 当前先按 chapter_number 对应卷序号，后续可再拆 chapter->volume mapping
    index = min(max(chapter_number - 1, 0), len(plans) - 1)
    return plans[index]


def next_task_sequence(root: Path) -> int:
    today_prefix = date.today().isoformat()
    pattern = re.compile(rf"{re.escape(today_prefix)}-(\d{{3}})")
    max_value = 0
    task_root = root / "01_inputs/tasks"
    if not task_root.exists():
        return 1
    for path in task_root.rglob("*.md"):
        match = pattern.search(path.name)
        if not match:
            continue
        max_value = max(max_value, int(match.group(1)))
    return max_value + 1


def build_generated_task_id(root: Path, chapter_number: int, scene_number: int, suffix: str = "auto") -> str:
    return f"{date.today().isoformat()}-{next_task_sequence(root):03d}_{scene_label(chapter_number, scene_number)}_{suffix}"


def latest_locked_scene(root: Path, chapter_number: int | None = None) -> str | None:
    chapter_dir = root / "03_locked/chapters"
    if not chapter_dir.exists():
        return None
    candidates: list[tuple[tuple[int, int], Path]] = []
    for path in chapter_dir.glob("ch*_scene*.md"):
        current_chapter, current_scene = extract_scene_progress(path.name)
        if current_chapter is None or current_scene is None:
            continue
        if chapter_number is not None and current_chapter != chapter_number:
            continue
        candidates.append(((current_chapter, current_scene), path))
    if not candidates:
        return None
    return str(sorted(candidates, key=lambda item: item[0])[-1][1].relative_to(root).as_posix())


def render_chapter_state(root: Path, chapter_number: int, previous_locked_file: str | None = None) -> str:
    human_input = load_human_input(root)
    story_state = load_story_state(root)
    volume = resolve_volume_context(root, chapter_number)
    cast = get_section(human_input, "cast")
    protagonist = cast.get("protagonist", {}) if isinstance(cast.get("protagonist"), dict) else get_section(human_input, "protagonist")
    protagonist_name = str(
        protagonist.get("name")
        or (((story_state.get("characters") or {}).get("protagonist") or {}).get("name") or "主角")
    ).strip() or "主角"
    known_facts = (((story_state.get("characters") or {}).get("protagonist") or {}).get("known_facts") or [])[:4]
    manual_required = get_section(human_input, "manual_required")
    story_blueprint = get_section(human_input, "story_blueprint")
    open_questions = (manual_required.get("open_questions") or human_input.get("open_questions") or [])[:4]
    must_avoid = (manual_required.get("must_avoid") or human_input.get("must_avoid") or [])[:4]
    previous_hint = previous_locked_file or latest_locked_scene(root, chapter_number=chapter_number - 1) or "00_manifest/novel_manifest.md"
    lines = [
        f"# {chapter_label(chapter_number)} 当前状态",
        "",
        "## 本章定位",
        f"- 所属卷：{volume.get('title') or '待定卷'}",
        f"- 本章功能：{volume.get('function') or '承接上一章并推进当前长线。'}",
        f"- 直接前文：{previous_hint}",
        "",
        "## 已锁定场景",
        "- [待生成本章锁定场景]",
        "",
        "## 当前主角状态",
        f"- 主角：{protagonist_name}",
        f"- 当前默认目标：{str(protagonist.get('goal') or story_blueprint.get('chapter_goal') or '先求活，再被卷入更大的局面。').strip()}",
    ]
    if known_facts:
        lines.extend(["", "## 已锁定线索"])
        lines.extend([f"- {str(item).strip()}" for item in known_facts if str(item).strip()])
    else:
        lines.extend(["", "## 已锁定线索", "- [待从前文与 story_state 回填]"])
    lines.extend(["", "## 暂不展开的内容"])
    hidden = [str(item).strip() for item in open_questions + must_avoid if str(item).strip()]
    if hidden:
        lines.extend([f"- {item}" for item in hidden])
    else:
        lines.append("- 不提前透支更高层级真相。")
    lines.extend(
        [
            "",
            "## scene01 建议目标",
            f"- 写出 {chapter_label(chapter_number)} 的开场承接，让局面在上一章基础上出现新的可验证变化。",
            "- 第一场既要重新落地人物生存处境，也要给出本章独有的新压力、新线索或新后果。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def ensure_chapter_state(root: Path, chapter_number: int, previous_locked_file: str | None = None) -> str:
    rel_path = chapter_state_path(chapter_number)
    path = root / rel_path
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_chapter_state(root, chapter_number, previous_locked_file=previous_locked_file), encoding="utf-8")
    return rel_path


def build_chapter_opening_task(
    root: Path,
    config: dict[str, Any],
    chapter_number: int,
    scene_number: int = 1,
    previous_locked_file: str | None = None,
) -> tuple[str, str]:
    state_path = ensure_chapter_state(root, chapter_number, previous_locked_file=previous_locked_file)
    task_id = build_generated_task_id(root, chapter_number, scene_number)
    human_input = load_human_input(root)
    project = get_section(human_input, "project", legacy="basic")
    cast = get_section(human_input, "cast")
    protagonist = cast.get("protagonist", {}) if isinstance(cast.get("protagonist"), dict) else get_section(human_input, "protagonist")
    blueprint = get_section(human_input, "story_blueprint")
    manual_required = get_section(human_input, "manual_required")
    protagonist_name = str(protagonist.get("name") or "主角").strip() or "主角"
    premise = str(project.get("premise") or "").strip()
    genre = str(project.get("genre") or "").strip()
    volume = resolve_volume_context(root, chapter_number)
    based_on = previous_locked_file or latest_locked_scene(root, chapter_number=chapter_number - 1) or "00_manifest/novel_manifest.md"
    goal = (
        f"写出第 {chapter_number} 章第 {scene_number} 个短场景，承接前文并为本章建立新的局面。"
        if scene_number == 1
        else f"继续推进第 {chapter_number} 章，写出 scene{scene_number:02d}。"
    )
    chapter_goal = str(blueprint.get("chapter_goal") or blueprint.get("first_chapter_goal") or "").strip()
    if volume.get("function"):
        goal = f"{goal} 本章重点：{volume['function']}"
    if chapter_goal:
        goal = f"{goal} 当前章节目标：{chapter_goal}"
    info_gain = [
        "补入至少一个只属于本章的新事实、新限制或新压力来源。",
        "让主角对当前局面产生新的理解、误判或行动边界。",
    ]
    if premise:
        info_gain.insert(0, f"保持与项目故事梗概一致：{premise}")
    constraints = [
        "保持连续小说 prose，不写说明、提纲或分镜。",
        "不要擅自跳出当前章的现实承接。",
        f"主角核心仍是 {protagonist_name}。",
    ]
    if genre:
        constraints.append(f"类型基调保持为：{genre}")
    for item in get_list(manual_required, "must_avoid", legacy=None) or get_list(human_input, "must_avoid", legacy=None):
        text = str(item).strip()
        if text:
            constraints.append(text)
    for item in get_list(blueprint, "taboo_beats"):
        constraints.append(f"避免拍点：{item}")
    preferred_length = str(((config.get("generation") or {}).get("preferred_length_override")) or "").strip()
    sections = [
        f"# task_id\n{task_id}",
        f"# goal\n{goal}",
        f"# based_on\n{based_on}",
        f"# chapter_state\n{state_path}",
        "# scene_purpose\n本场结束时必须形成新的章内起点，不能只是重复上章余波。",
        "# required_information_gain\n" + "\n".join(f"- {item}" for item in info_gain),
        "# required_plot_progress\n本场必须把上一章后的局面真正往前推一步，为本章建立新的现实问题。",
        "# required_decision_shift\n主角必须做出一个会影响本章后续处理方式的新动作或新决定。",
        "# required_state_change\n- 至少一个状态变量改变：已知信息 / 风险等级 / 行动计划 / 关系态势 / 物件位置。",
        "# constraints\n" + "\n".join(f"- {item}" for item in constraints),
    ]
    required_beats = get_list(blueprint, "required_beats")
    if required_beats:
        sections.insert(
            -1,
            "# required_information_gain\n" + "\n".join(f"- {item}" for item in (info_gain + required_beats)),
        )
        sections.pop(5)
    if preferred_length:
        sections.append(f"# preferred_length\n{preferred_length}")
    sections.append(f"# output_target\n{draft_output_path(chapter_number, scene_number)}")
    return task_id, "\n\n".join(sections) + "\n"
