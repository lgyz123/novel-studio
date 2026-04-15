import json
from pathlib import Path
from typing import Any


EXPECTED_SELECTED_SKILLS: dict[str, list[str]] = {
    "planning_bootstrap": ["worldbuilding", "scene-outline"],
    "character_creation": ["character-design", "naming"],
    "timeline_bootstrap": ["timeline-history"],
}


def audit_skill_router_result(phase: str, result: dict[str, Any]) -> dict[str, Any]:
    selected = result.get("selected_skills", []) if isinstance(result, dict) else []
    selected_names = [
        str(item.get("skill") or "").strip()
        for item in selected
        if isinstance(item, dict) and str(item.get("skill") or "").strip()
    ]

    major_issues: list[str] = []
    minor_issues: list[str] = []
    expected = EXPECTED_SELECTED_SKILLS.get(phase, [])

    if expected:
        missing = [skill for skill in expected if skill not in selected_names]
        if missing:
            major_issues.append(f"{phase} router 漏选关键 skill：{'、'.join(missing)}。")

    if phase == "scene_writing":
        if "continuity-guard" not in selected_names:
            major_issues.append("scene_writing router 漏选 `continuity-guard`，会带来明显连续性风险。")
        if len(selected_names) > 3:
            major_issues.append(f"scene_writing router 选择了 {len(selected_names)} 个 skill，已超过约定上限 3 个。")
    else:
        if len(selected_names) > 2:
            major_issues.append(f"{phase} router 选择了 {len(selected_names)} 个 skill，已超过 planning 阶段约定上限 2 个。")

    if not major_issues and selected_names:
        minor_issues.append(f"{phase} router 当前启用：{'、'.join(selected_names)}。")

    return {
        "phase": phase,
        "selected_skills": selected_names,
        "major_issues": major_issues,
        "minor_issues": minor_issues,
        "is_ok": not major_issues,
    }


def render_skill_audit_markdown(audits: list[dict[str, Any]], heading: str = "# skill audit") -> str:
    lines = [heading, ""]
    for item in audits:
        lines.extend(
            [
                f"## {item.get('phase', 'unknown')}",
                f"- selected_skills：{'、'.join(item.get('selected_skills', [])) or '无'}",
            ]
        )
        major = item.get("major_issues", [])
        minor = item.get("minor_issues", [])
        if major:
            lines.append("- major_issues：")
            lines.extend([f"  - {entry}" for entry in major])
        else:
            lines.append("- major_issues：无")
        if minor:
            lines.append("- minor_issues：")
            lines.extend([f"  - {entry}" for entry in minor])
        else:
            lines.append("- minor_issues：无")
        lines.append(f"- is_ok：{item.get('is_ok')}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def save_skill_audit_outputs(root: Path, rel_stem: str, audits: list[dict[str, Any]]) -> dict[str, str]:
    json_path = root / f"{rel_stem}.json"
    md_path = root / f"{rel_stem}.md"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"audits": audits}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_skill_audit_markdown(audits), encoding="utf-8")
    return {
        "json_file": str(json_path.relative_to(root)),
        "md_file": str(md_path.relative_to(root)),
    }
