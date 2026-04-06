import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


STORY_STATE_REL_PATH = "03_locked/state/story_state.json"
STORY_STATE_HISTORY_DIR = "03_locked/state/history"


class TimelineState(BaseModel):
    current_book_time: str = "unknown"
    recent_events: list[str] = Field(default_factory=list)


class CharacterState(BaseModel):
    location: str = "unknown"
    physical_state: str = "unknown"
    mental_state: str = "unknown"
    known_facts: list[str] = Field(default_factory=list)
    active_goals: list[str] = Field(default_factory=list)
    open_tensions: list[str] = Field(default_factory=list)


class PromiseState(BaseModel):
    id: str
    description: str
    introduced_in: str
    expected_payoff_window: str


class SecretState(BaseModel):
    id: str
    description: str
    revealed_in: str
    status: str


class ItemState(BaseModel):
    id: str
    name: str
    owner: str
    status: str
    last_seen_in: str
    notes: str = ""


class RelationshipDelta(BaseModel):
    id: str
    source: str
    target: str
    delta: str
    introduced_in: str
    status: str = "active"


class StoryState(BaseModel):
    timeline: TimelineState = Field(default_factory=TimelineState)
    characters: dict[str, CharacterState] = Field(default_factory=dict)
    unresolved_promises: list[PromiseState] = Field(default_factory=list)
    revealed_secrets: list[SecretState] = Field(default_factory=list)
    items: list[ItemState] = Field(default_factory=list)
    relationship_deltas: list[RelationshipDelta] = Field(default_factory=list)
    last_locked_scene: str = ""

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
    def from_dict(cls, data: dict[str, Any]) -> "StoryState":
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls.parse_obj(data)

    @classmethod
    def load(cls, path: Path) -> "StoryState":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def read_text(root: Path, rel_path: str | None) -> str:
    if not rel_path:
        return ""
    return (root / rel_path).read_text(encoding="utf-8")


def parse_markdown_sections(markdown_text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections[current_section] = []
            continue
        if current_section and line.strip().startswith("-"):
            sections[current_section].append(line.strip()[1:].strip())

    return sections


def dedupe_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def merge_keyed_models(existing: list[BaseModel], incoming: list[BaseModel]) -> list[BaseModel]:
    merged: dict[str, BaseModel] = {}
    for item in existing:
        merged[getattr(item, "id")] = item
    for item in incoming:
        merged[getattr(item, "id")] = item
    return list(merged.values())


def scene_stem_from_locked_file(locked_file: str) -> str:
    return Path(locked_file).stem


def event_id_from_scene(scene_stem: str) -> str:
    match = re.search(r"scene(\d+)", scene_stem)
    if match:
        return f"EVENT-{int(match.group(1)):03d}"
    return f"EVENT-{scene_stem.upper()}"


def promise_id(index: int) -> str:
    return f"PROMISE-{index:03d}"


def secret_id(index: int) -> str:
    return f"SECRET-{index:03d}"


def item_id(index: int) -> str:
    return f"ITEM-{index:03d}"


def relationship_id(index: int) -> str:
    return f"REL-{index:03d}"


def infer_book_time(chapter_state_text: str, locked_text: str, existing_value: str) -> str:
    combined = f"{chapter_state_text}\n{locked_text}"
    if "次日" in combined:
        if any(marker in combined for marker in ("夜", "夜里", "夜色", "夜间")):
            return "次日夜间"
        return "次日白天"
    if any(marker in locked_text for marker in ("日头", "日光", "天光", "额角的汗", "白天")):
        return "白天"
    if any(marker in locked_text for marker in ("夜", "夜里", "夜色", "灯下")):
        return "夜间"
    return existing_value or "unknown"


def infer_location(task_text: str, locked_text: str, existing_value: str) -> str:
    combined = f"{task_text}\n{locked_text}"
    location_rules = [
        ("码头", "码头"),
        ("运河", "运河边"),
        ("乱葬岗", "乱葬岗"),
        ("住处", "住处"),
        ("棚下", "码头棚下"),
    ]
    for marker, label in location_rules:
        if marker in combined:
            return label
    return existing_value or "unknown"


def summarize_physical_state(protagonist_bullets: list[str], locked_text: str, existing_value: str) -> str:
    tags: list[str] = []
    combined = " ".join(protagonist_bullets) + "\n" + locked_text
    if any(marker in combined for marker in ("疲惫", "酸", "发木", "劳损", "寒冷", "潮气")):
        tags.append("疲惫")
    if any(marker in combined for marker in ("底层求活", "做活", "劳作")):
        tags.append("持续劳作")
    if any(marker in combined for marker in ("并未麻木", "没有麻木")):
        tags.append("未麻木")
    return "、".join(dedupe_strings(tags)) or existing_value or "unknown"


def summarize_mental_state(protagonist_bullets: list[str], locked_text: str, existing_value: str) -> str:
    tags: list[str] = []
    combined = " ".join(protagonist_bullets) + "\n" + locked_text
    if any(marker in combined for marker in ("克制", "压", "低烈度")):
        tags.append("克制")
    if any(marker in combined for marker in ("放不下", "阿绣", "停顿", "牵住", "牵动")):
        tags.append("被“阿绣”持续牵动")
    if any(marker in combined for marker in ("未形成明确行动", "未展开主动追查", "尚未升级成主动追查", "不升级为明确调查")):
        tags.append("尚未转为调查")
    return "、".join(dedupe_strings(tags)) or existing_value or "unknown"


def infer_active_goals(task_text: str, protagonist_bullets: list[str], existing_items: list[str]) -> list[str]:
    goals = list(existing_items)
    if any(marker in task_text for marker in ("底层求活", "求活日常", "码头")):
        goals.append("维持日常求活与码头做活")
    if any(marker in " ".join(protagonist_bullets) for marker in ("尚未形成明确调查", "尚未形成行动计划", "无法轻易放下")):
        goals.append("在不主动追查的前提下继续压住“阿绣”这条线")
    return dedupe_strings(goals)


def infer_open_tensions(protagonist_bullets: list[str], existing_items: list[str]) -> list[str]:
    tensions = list(existing_items)
    for bullet in protagonist_bullets:
        if any(marker in bullet for marker in ("尚未", "无法", "放不下", "牵动", "不再只", "仍未")):
            tensions.append(bullet)
    return dedupe_strings(tensions)


def infer_revealed_secrets(chapter_sections: dict[str, list[str]], scene_stem: str, existing: list[SecretState]) -> list[SecretState]:
    existing_map = {item.id: item for item in existing}
    results = list(existing)
    clues = chapter_sections.get("已锁定线索", [])
    index = len(existing_map) + 1
    for clue in clues:
        if "平安符背面的“阿绣”" in clue and not any(item.description == clue for item in results):
            results.append(
                SecretState(
                    id=secret_id(index),
                    description=clue,
                    revealed_in=scene_stem,
                    status="active",
                )
            )
            index += 1
    return results


def infer_items(chapter_sections: dict[str, list[str]], scene_stem: str, existing: list[ItemState]) -> list[ItemState]:
    item_specs = [
        ("红绳", "红绳", "孟浮灯", "贴身保留", "“阿绣”线索的物理载体之一"),
        ("平安符", "平安符", "孟浮灯", "贴身保留", "背面刻有“阿绣”二字"),
        ("线头", "线头", "孟浮灯", "袖口暂留", "scene09 起被下意识保留"),
    ]
    existing_by_name = {item.name: item for item in existing}
    results = list(existing)
    next_index = len(existing_by_name) + 1
    source_text = " ".join(chapter_sections.get("已锁定线索", []))
    for keyword, name, owner, status, notes in item_specs:
        if keyword in source_text and name not in existing_by_name:
            results.append(
                ItemState(
                    id=item_id(next_index),
                    name=name,
                    owner=owner,
                    status=status,
                    last_seen_in=scene_stem,
                    notes=notes,
                )
            )
            next_index += 1
    for item in results:
        if item.name == "线头" and "scene09" in scene_stem:
            item.status = "袖口暂留"
            item.last_seen_in = scene_stem
    return results


def infer_relationship_deltas(chapter_sections: dict[str, list[str]], scene_stem: str, existing: list[RelationshipDelta]) -> list[RelationshipDelta]:
    results = list(existing)
    description = "“阿绣”从被记住的名字，逐步转为会轻微牵住孟浮灯现实动作的隐性张力。"
    if any(item.delta == description for item in results):
        for item in results:
            if item.delta == description:
                item.introduced_in = scene_stem
        return results
    results.append(
        RelationshipDelta(
            id=relationship_id(len(results) + 1),
            source="孟浮灯",
            target="阿绣",
            delta=description,
            introduced_in=scene_stem,
            status="active",
        )
    )
    return results


def infer_unresolved_promises(chapter_sections: dict[str, list[str]], scene_stem: str, existing: list[PromiseState]) -> list[PromiseState]:
    results = list(existing)
    existing_descriptions = {item.description for item in results}
    payoff_map = {
        "不揭示阿绣身份": "chapter_01_to_03",
        "不展开司命体系": "chapter_02_to_05",
        "不急于抛出主线真相": "chapter_02_to_06",
    }
    for text in chapter_sections.get("暂不展开的内容", []):
        if text in existing_descriptions:
            continue
        results.append(
            PromiseState(
                id=promise_id(len(results) + 1),
                description=text,
                introduced_in=scene_stem,
                expected_payoff_window=payoff_map.get(text, "chapter_future"),
            )
        )
    return results


def build_story_state_patch(existing: StoryState, task_text: str, chapter_state_text: str, locked_text: str, locked_file: str) -> StoryState:
    scene_stem = scene_stem_from_locked_file(locked_file)
    chapter_sections = parse_markdown_sections(chapter_state_text)
    protagonist_bullets = chapter_sections.get("当前主角状态", [])
    protagonist = existing.characters.get("protagonist", CharacterState())

    event_id = event_id_from_scene(scene_stem)
    recent_events = dedupe_strings(existing.timeline.recent_events + [event_id])

    patch = StoryState(
        timeline=TimelineState(
            current_book_time=infer_book_time(chapter_state_text, locked_text, existing.timeline.current_book_time),
            recent_events=recent_events,
        ),
        characters={
            "protagonist": CharacterState(
                location=infer_location(task_text, locked_text, protagonist.location),
                physical_state=summarize_physical_state(protagonist_bullets, locked_text, protagonist.physical_state),
                mental_state=summarize_mental_state(protagonist_bullets, locked_text, protagonist.mental_state),
                known_facts=dedupe_strings(protagonist.known_facts + chapter_sections.get("已锁定线索", [])),
                active_goals=infer_active_goals(task_text, protagonist_bullets, protagonist.active_goals),
                open_tensions=infer_open_tensions(protagonist_bullets, protagonist.open_tensions),
            )
        },
        unresolved_promises=infer_unresolved_promises(chapter_sections, scene_stem, existing.unresolved_promises),
        revealed_secrets=infer_revealed_secrets(chapter_sections, scene_stem, existing.revealed_secrets),
        items=infer_items(chapter_sections, scene_stem, existing.items),
        relationship_deltas=infer_relationship_deltas(chapter_sections, scene_stem, existing.relationship_deltas),
        last_locked_scene=scene_stem,
    )
    return patch


def merge_story_state(existing: StoryState, patch: StoryState) -> StoryState:
    merged = StoryState.from_dict(existing.to_dict())
    merged.timeline.current_book_time = patch.timeline.current_book_time or merged.timeline.current_book_time
    merged.timeline.recent_events = dedupe_strings(merged.timeline.recent_events + patch.timeline.recent_events)

    for character_key, patch_character in patch.characters.items():
        current = merged.characters.get(character_key, CharacterState())
        current.location = patch_character.location or current.location
        current.physical_state = patch_character.physical_state or current.physical_state
        current.mental_state = patch_character.mental_state or current.mental_state
        current.known_facts = dedupe_strings(current.known_facts + patch_character.known_facts)
        current.active_goals = dedupe_strings(current.active_goals + patch_character.active_goals)
        current.open_tensions = dedupe_strings(current.open_tensions + patch_character.open_tensions)
        merged.characters[character_key] = current

    merged.unresolved_promises = merge_keyed_models(merged.unresolved_promises, patch.unresolved_promises)
    merged.revealed_secrets = merge_keyed_models(merged.revealed_secrets, patch.revealed_secrets)
    merged.items = merge_keyed_models(merged.items, patch.items)
    merged.relationship_deltas = merge_keyed_models(merged.relationship_deltas, patch.relationship_deltas)
    merged.last_locked_scene = patch.last_locked_scene or merged.last_locked_scene
    return merged


def flatten_json(value: Any, prefix: str = "") -> dict[str, str]:
    items: dict[str, str] = {}
    if isinstance(value, dict):
        for key in sorted(value.keys()):
            next_prefix = f"{prefix}.{key}" if prefix else key
            items.update(flatten_json(value[key], next_prefix))
        return items
    if isinstance(value, list):
        for index, item in enumerate(value):
            next_prefix = f"{prefix}[{index}]"
            items.update(flatten_json(item, next_prefix))
        if not value:
            items[prefix] = "[]"
        return items
    items[prefix] = json.dumps(value, ensure_ascii=False)
    return items


def build_story_state_diff(old_state: StoryState | None, new_state: StoryState, scene_stem: str) -> str:
    old_flat = flatten_json(old_state.to_dict() if old_state is not None else {})
    new_flat = flatten_json(new_state.to_dict())

    added = []
    changed = []
    removed = []

    for key, value in new_flat.items():
        if key not in old_flat:
            added.append(f"- {key}: {value}")
        elif old_flat[key] != value:
            changed.append(f"- {key}: {old_flat[key]} -> {value}")

    for key, value in old_flat.items():
        if key not in new_flat:
            removed.append(f"- {key}: {value}")

    lines = [f"# {scene_stem} story_state diff", ""]
    if added:
        lines.extend(["## Added", *added, ""])
    if changed:
        lines.extend(["## Changed", *changed, ""])
    if removed:
        lines.extend(["## Removed", *removed, ""])
    if not (added or changed or removed):
        lines.extend(["## No Changes", "- 本次 lock 未引入 story_state 变更", ""])
    return "\n".join(lines).strip() + "\n"


def load_story_state(root: Path) -> StoryState:
    path = root / STORY_STATE_REL_PATH
    if not path.exists():
        return StoryState(characters={"protagonist": CharacterState()})
    state = StoryState.load(path)
    if "protagonist" not in state.characters:
        state.characters["protagonist"] = CharacterState()
    return state


def save_story_state_files(root: Path, state: StoryState, scene_stem: str, previous_state: StoryState | None) -> tuple[str, str, str]:
    story_state_path = root / STORY_STATE_REL_PATH
    diff_rel_path = f"{STORY_STATE_HISTORY_DIR}/{scene_stem}_story_state_diff.md"
    snapshot_rel_path = f"{STORY_STATE_HISTORY_DIR}/{scene_stem}_story_state_snapshot.json"

    state.save(story_state_path)
    (root / diff_rel_path).parent.mkdir(parents=True, exist_ok=True)
    (root / diff_rel_path).write_text(
        build_story_state_diff(previous_state, state, scene_stem),
        encoding="utf-8",
    )
    (root / snapshot_rel_path).write_text(state.to_json(), encoding="utf-8")
    return STORY_STATE_REL_PATH, diff_rel_path, snapshot_rel_path


def update_story_state_on_lock(
    root: Path,
    task_text: str,
    locked_file: str,
    chapter_state_path: str | None = None,
) -> dict[str, str]:
    previous_state = load_story_state(root)
    chapter_state_text = read_text(root, chapter_state_path)
    locked_text = read_text(root, locked_file)
    patch = build_story_state_patch(previous_state, task_text, chapter_state_text, locked_text, locked_file)
    merged = merge_story_state(previous_state, patch)
    scene_stem = scene_stem_from_locked_file(locked_file)
    story_state_rel_path, diff_rel_path, snapshot_rel_path = save_story_state_files(root, merged, scene_stem, previous_state)
    return {
        "story_state_file": story_state_rel_path,
        "story_state_diff_file": diff_rel_path,
        "story_state_snapshot_file": snapshot_rel_path,
    }
