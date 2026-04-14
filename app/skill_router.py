import re
from typing import Any


def extract_markdown_field(task_text: str, field_name: str) -> str | None:
    pattern = rf"(?ms)^#\s*{re.escape(field_name)}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, task_text)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _skill_entry(skill: str, mode: str, score: float, reason: str) -> dict[str, Any]:
    return {
        "skill": skill,
        "mode": mode,
        "score": round(score, 2),
        "reason": reason,
    }


def route_writer_skills(
    *,
    phase: str,
    task_text: str,
    project_manifest_text: str = "",
    state_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state_signals = state_signals or {}
    combined = "\n".join([task_text, project_manifest_text]).strip()
    genre_tags: list[str] = []
    trope_tags: list[str] = []
    demand_tags: list[str] = []
    selected_skills: list[dict[str, Any]] = []
    rejected_candidates: list[dict[str, Any]] = []
    risk_flags: list[str] = []

    if _contains_any(combined, ["玄幻", "仙侠", "修真", "功法", "境界", "宗门"]):
        genre_tags.append("xianxia")
    if _contains_any(combined, ["言情", "cp", "暧昧", "表白", "救赎", "he"]):
        genre_tags.append("romance")
    if _contains_any(combined, ["悬疑", "线索", "案件", "惊悚", "诡案"]):
        genre_tags.append("mystery")
    if _contains_any(combined, ["abo", "alpha", "omega", "信息素"]):
        trope_tags.append("abo")
    if _contains_any(combined, ["系统", "任务", "面板", "金手指"]):
        trope_tags.append("system")

    if phase == "planning_bootstrap":
        demand_tags.extend(["planning", "worldbuilding", "outline-driven"])
        selected_skills.append(
            _skill_entry(
                "worldbuilding",
                "institutional",
                0.92,
                "planning/bootstrap 阶段需要把抽象设定补成可执行的世界观补丁。",
            )
        )
        selected_skills.append(
            _skill_entry(
                "scene-outline",
                "chapter-outline",
                0.88,
                "planning/bootstrap 阶段需要把章节目标压成可写的结构骨架。",
            )
        )
        rejected_candidates.append(
            _skill_entry(
                "continuity-guard",
                "scene-canon",
                0.24,
                "此阶段以补 planning proposal 为主，还不是正文落稿校验阶段。",
            )
        )

    elif phase == "scene_writing":
        demand_tags.extend(["continuity", "scene-writing"])
        if _contains_any(task_text, ["人物设定", "角色卡", "人物关系", "外貌", "性格"]):
            demand_tags.append("character")
        if _contains_any(task_text, ["取名", "命名", "名字", "名称", "称号", "年号"]):
            demand_tags.append("naming")
        if extract_markdown_field(task_text, "chapter_state") or state_signals:
            selected_skills.append(
                _skill_entry(
                    "continuity-guard",
                    "scene-canon",
                    0.95,
                    "scene 写作依赖 chapter_state、story_state 或 tracker 承接，默认必须启用 continuity-guard。",
                )
            )
        else:
            selected_skills.append(
                _skill_entry(
                    "continuity-guard",
                    "scene-canon",
                    0.81,
                    "scene 写作默认挂 continuity-guard，避免状态和时间承接静默漂移。",
                )
            )

        if _contains_any(task_text, ["人物设定", "角色卡", "人物关系", "外貌", "性格"]):
            selected_skills.append(
                _skill_entry(
                    "character-design",
                    "supporting-role",
                    0.67,
                    "当前任务显式涉及人物设定或关系描写，补充 character-design 可让人物功能与行为锚点更稳定。",
                )
            )

        if _contains_any(task_text, ["取名", "命名", "名字", "名称", "称号", "年号"]):
            selected_skills.append(
                _skill_entry(
                    "naming",
                    "person",
                    0.64,
                    "当前任务包含明确命名需求，应补充 naming 候选与风格约束。",
                )
            )

        if _contains_any(task_text, ["scene_purpose", "required_information_gain", "required_plot_progress"]):
            rejected_candidates.append(
                _skill_entry(
                    "scene-outline",
                    "scene-contract",
                    0.42,
                    "当前由 task contract 直接约束场景，暂不重复加载 scene-outline。",
                )
            )
        rejected_candidates.append(
            _skill_entry(
                "worldbuilding",
                "institutional",
                0.2,
                "当前是正文落稿阶段，世界观补丁已应在 planning 阶段提前生成。",
            )
            )

    else:
        risk_flags.append("unknown_phase")

    if len(selected_skills) > 3:
        selected_skills = selected_skills[:3]
        risk_flags.append("selected_skill_limit_applied")

    return {
        "phase": phase,
        "genre_tags": genre_tags,
        "trope_tags": trope_tags,
        "demand_tags": demand_tags,
        "selected_skills": selected_skills,
        "rejected_candidates": rejected_candidates,
        "risk_flags": risk_flags,
    }


def render_skill_router_markdown(result: dict[str, Any], heading: str = "# skill router") -> str:
    lines = [
        heading,
        "",
        f"- phase：{result.get('phase', 'unknown')}",
        f"- genre_tags：{'、'.join(result.get('genre_tags', [])) or '无'}",
        f"- trope_tags：{'、'.join(result.get('trope_tags', [])) or '无'}",
        f"- demand_tags：{'、'.join(result.get('demand_tags', [])) or '无'}",
        "",
        "## selected_skills",
    ]
    selected = result.get("selected_skills", [])
    if selected:
        for item in selected:
            lines.append(
                f"- {item.get('skill')}｜mode={item.get('mode')}｜score={item.get('score')}｜{item.get('reason')}"
            )
    else:
        lines.append("- 无")

    lines.extend(["", "## rejected_candidates"])
    rejected = result.get("rejected_candidates", [])
    if rejected:
        for item in rejected:
            lines.append(
                f"- {item.get('skill')}｜mode={item.get('mode')}｜score={item.get('score')}｜{item.get('reason')}"
            )
    else:
        lines.append("- 无")

    risk_flags = result.get("risk_flags", [])
    lines.extend(["", "## risk_flags", f"- {'、'.join(risk_flags) if risk_flags else '无'}"])
    return "\n".join(lines).strip() + "\n"
