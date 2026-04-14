import re
from pathlib import Path

DEFAULT_SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_REFERENCE_CONFIG: dict[str, dict[str, object]] = {
    "continuity-guard": {
        "references": ["checklist.md", "conflicts.md"],
        "body_max_chars": 800,
        "reference_max_chars": 320,
    },
    "character-design": {
        "references": ["cards.md", "tension.md"],
        "body_max_chars": 760,
        "reference_max_chars": 280,
    },
    "naming": {
        "references": ["person.md", "world.md"],
        "body_max_chars": 720,
        "reference_max_chars": 260,
    },
    "scene-outline": {
        "references": ["contract-patterns.md", "chapter-shapes.md"],
        "body_max_chars": 750,
        "reference_max_chars": 320,
    },
    "worldbuilding": {
        "references": ["patch-patterns.md", "writer-hooks.md"],
        "body_max_chars": 750,
        "reference_max_chars": 320,
    },
}


def _strip_frontmatter(text: str) -> str:
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return text.strip()
    match = re.match(r"(?s)^---\n.*?\n---\n?", stripped)
    if not match:
        return text.strip()
    return stripped[match.end():].strip()


def _resolve_skill_file(root: Path, rel_path: str) -> Path:
    primary = root / rel_path
    if primary.exists():
        return primary
    fallback = DEFAULT_SKILL_ROOT / rel_path
    if fallback.exists():
        return fallback
    return primary


def read_skill_body(root: Path, skill_name: str) -> tuple[str, str]:
    rel_path = f"skills/{skill_name}/SKILL.md"
    path = _resolve_skill_file(root, rel_path)
    text = path.read_text(encoding="utf-8")
    return rel_path, _strip_frontmatter(text)


def read_skill_reference(root: Path, skill_name: str, reference_name: str) -> tuple[str, str]:
    rel_path = f"skills/{skill_name}/references/{reference_name}"
    path = _resolve_skill_file(root, rel_path)
    text = path.read_text(encoding="utf-8").strip()
    return rel_path, text


def clip_text(text: str, max_chars: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rstrip() + "\n\n[已截断]"


def build_skill_section(
    root: Path,
    skill_name: str,
    *,
    heading: str,
    body_max_chars: int = 900,
    references: list[str] | None = None,
    reference_max_chars: int = 500,
) -> str:
    skill_path, skill_body = read_skill_body(root, skill_name)
    lines = [
        heading,
        f"来源文件：{skill_path}",
        "",
        clip_text(skill_body, body_max_chars),
    ]

    for reference_name in references or []:
        ref_path, ref_text = read_skill_reference(root, skill_name, reference_name)
        lines.extend(
            [
                "",
                f"参考：{ref_path}",
                "",
                clip_text(ref_text, reference_max_chars),
            ]
        )

    return "\n".join(lines).strip() + "\n"


def build_selected_skill_sections(root: Path, selected_skills: list[dict], *, heading_prefix: str = "# writer skill") -> str:
    sections: list[str] = []
    seen: set[str] = set()
    for item in selected_skills:
        skill_name = str(item.get("skill") or "").strip()
        if not skill_name or skill_name in seen:
            continue
        seen.add(skill_name)
        config = SKILL_REFERENCE_CONFIG.get(skill_name, {})
        sections.append(
            build_skill_section(
                root,
                skill_name,
                heading=f"{heading_prefix}：{skill_name}",
                body_max_chars=int(config.get("body_max_chars", 900)),
                references=list(config.get("references", [])),
                reference_max_chars=int(config.get("reference_max_chars", 500)),
            ).strip()
        )
    return "\n\n".join(sections).strip()
