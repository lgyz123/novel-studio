from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
HUMAN_INPUT_PATH = "01_inputs/human_input.yaml"


def load_yaml_if_exists(root: Path, rel_path: str) -> dict[str, Any]:
    path = root / rel_path
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_human_input(root: Path = ROOT) -> dict[str, Any]:
    return load_yaml_if_exists(root, HUMAN_INPUT_PATH)


def _normalize_lines(values: Any) -> list[str]:
    if isinstance(values, str):
        text = values.strip()
        return [text] if text else []
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def render_human_input_markdown(data: dict[str, Any] | None) -> str:
    payload = data if isinstance(data, dict) else {}
    if not payload:
        return ""

    lines = ["# Human Input", "- 说明：以下内容属于人工明确指定的项目输入，自动流程默认优先服从这一层。"]

    basic = payload.get("basic", {}) if isinstance(payload.get("basic"), dict) else {}
    if basic:
        lines.extend(["", "## 基本信息"])
        field_labels = {
            "novel_title": "小说名",
            "genre": "类型",
            "audience": "受众",
            "style": "风格",
            "hook": "一句话卖点",
            "premise": "故事梗概",
        }
        for field, label in field_labels.items():
            value = str(basic.get(field) or "").strip()
            if value:
                lines.append(f"- {label}：{value}")

    protagonist = payload.get("protagonist", {}) if isinstance(payload.get("protagonist"), dict) else {}
    if protagonist:
        lines.extend(["", "## 主角"])
        for field, label in (("name", "姓名"), ("role", "定位"), ("description", "描述"), ("goal", "当前目标")):
            value = str(protagonist.get(field) or "").strip()
            if value:
                lines.append(f"- {label}：{value}")

    supporting = payload.get("supporting_roles", []) if isinstance(payload.get("supporting_roles"), list) else []
    supporting_lines = []
    for entry in supporting:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        role = str(entry.get("role") or "").strip()
        desc = str(entry.get("description") or "").strip()
        parts = [part for part in [name, role, desc] if part]
        if parts:
            supporting_lines.append("｜".join(parts))
    if supporting_lines:
        lines.extend(["", "## 次要角色"])
        lines.extend([f"- {item}" for item in supporting_lines[:8]])

    world = payload.get("world", {}) if isinstance(payload.get("world"), dict) else {}
    if world:
        lines.extend(["", "## 世界与约束"])
        for field, label in (("era", "时代"), ("setting", "主要舞台"), ("power_system", "力量体系"), ("taboos", "禁区")):
            value = str(world.get(field) or "").strip()
            if value:
                lines.append(f"- {label}：{value}")

    for field, heading in (
        ("must_have", "## 必须出现"),
        ("must_avoid", "## 必须避免"),
        ("open_questions", "## 当前待定"),
    ):
        items = _normalize_lines(payload.get(field))
        if items:
            lines.extend(["", heading])
            lines.extend([f"- {item}" for item in items])

    manual_refs = _normalize_lines(payload.get("manual_reference_files"))
    if manual_refs:
        lines.extend(["", "## 人工指定参考文件"])
        lines.extend([f"- {item}" for item in manual_refs])

    return "\n".join(lines).strip() + "\n"

