import json
import re
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


STORY_STATE_REL_PATH = "03_locked/state/story_state.json"
STORY_STATE_HISTORY_DIR = "03_locked/state/history"
STORY_STATE_PROPOSAL_DIR = "02_working/canon_updates"


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


class CharacterStatePatch(BaseModel):
    location: str | None = None
    physical_state: str | None = None
    mental_state: str | None = None
    known_facts_to_add: list[str] = Field(default_factory=list)
    active_goals_to_add: list[str] = Field(default_factory=list)
    open_tensions_to_add: list[str] = Field(default_factory=list)


class StoryStatePatchProposal(BaseModel):
    task_id: str
    locked_file: str
    based_on_state: str
    timeline_updates: dict[str, Any] = Field(default_factory=dict)
    character_updates: dict[str, CharacterStatePatch] = Field(default_factory=dict)
    unresolved_promises_to_add: list[PromiseState] = Field(default_factory=list)
    revealed_secrets_to_add: list[SecretState] = Field(default_factory=list)
    item_updates: list[ItemState] = Field(default_factory=list)
    relationship_deltas_to_add: list[RelationshipDelta] = Field(default_factory=list)
    decision_reason: str

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")


class StoryStateBootstrapConfig(BaseModel):
    protagonist_name: str = "主角"
    location_hints: list[str] = Field(default_factory=list)


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def read_text(root: Path, rel_path: str | None) -> str:
    if not rel_path:
        return ""
    return (root / rel_path).read_text(encoding="utf-8")


def extract_markdown_field(task_text: str, field_name: str) -> str | None:
    pattern = rf"(?ms)^#\s*{field_name}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, task_text)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


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


def scene_sort_key_from_name(name: str) -> tuple[int, int]:
    match = re.search(r"ch(\d+)_scene(\d+)", name)
    if not match:
        return (9999, 9999)
    return (int(match.group(1)), int(match.group(2)))


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


def infer_future_window(scene_stem: str) -> str:
    match = re.search(r"ch(\d+)_scene(\d+)", scene_stem)
    if not match:
        return "later"
    chapter_number = int(match.group(1))
    scene_number = int(match.group(2))
    return f"chapter_{chapter_number:02d}_scene_{scene_number + 1:02d}_onward"


def infer_chapter_state_path_from_scene(scene_stem: str) -> str:
    match = re.search(r"(ch\d+)_scene\d+", scene_stem)
    if not match:
        return "03_locked/canon/ch01_state.md"
    return f"03_locked/canon/{match.group(1)}_state.md"


def find_task_file_for_scene(root: Path, scene_stem: str) -> str | None:
    generated_dir = root / "01_inputs/tasks/generated"
    if not generated_dir.exists():
        return None

    exact_matches = sorted(generated_dir.glob(f"*_{scene_stem}_auto.md"))
    if exact_matches:
        return exact_matches[0].relative_to(root).as_posix()

    for path in generated_dir.glob("*.md"):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        output_target = extract_markdown_field(text, "output_target") or ""
        output_stem = Path(output_target).stem
        output_stem = re.sub(r"(?:_v\d+)+$", "", output_stem)
        output_stem = re.sub(r"_rewrite\d*$", "", output_stem)
        if output_stem == scene_stem:
            return path.relative_to(root).as_posix()
    return None


def build_synthetic_task_text(scene_stem: str, chapter_state_path: str, locked_file: str) -> str:
    return (
        f"# task_id\nrebuild_{scene_stem}\n\n"
        f"# goal\n基于已锁定正文重建 story state。\n\n"
        f"# based_on\n{locked_file}\n\n"
        f"# chapter_state\n{chapter_state_path}\n"
    )


def resolve_task_text_for_scene(root: Path, scene_stem: str, locked_file: str) -> tuple[str, str | None]:
    task_file = find_task_file_for_scene(root, scene_stem)
    chapter_state_path = infer_chapter_state_path_from_scene(scene_stem)
    if task_file:
        return read_text(root, task_file), task_file
    return build_synthetic_task_text(scene_stem, chapter_state_path, locked_file), None


def clear_story_state_outputs(root: Path) -> None:
    story_state_path = root / STORY_STATE_REL_PATH
    history_dir = root / STORY_STATE_HISTORY_DIR
    proposal_dir = root / STORY_STATE_PROPOSAL_DIR

    if story_state_path.exists():
        story_state_path.unlink()
    if history_dir.exists():
        shutil.rmtree(history_dir)
    if proposal_dir.exists():
        for path in proposal_dir.glob("*_story_state_patch.json"):
            path.unlink()


def extract_named_terms(text: str) -> list[str]:
    quoted_terms = re.findall(r"[“\"]([^”\"]{1,12})[”\"]", text)
    bare_name_terms = re.findall(r"([一-龥]{2,4})", text)
    candidates = quoted_terms + bare_name_terms
    filtered = []
    skip = {"当前", "状态", "场景", "chapter", "scene"}
    for term in candidates:
        term = term.strip()
        if len(term) < 2 or term in skip:
            continue
        filtered.append(term)
    return dedupe_strings(filtered)


def extract_character_name_candidates(text: str) -> list[str]:
    candidates = re.findall(r"([一-龥]{2,4})(?=(?:仍|在|把|将|正|又|先|便|停顿|走|回|看|听|闻|摸|捡|拾|决定|想|没|不|已|会))", str(text or ""))
    skip = {"当前", "状态", "场景", "线索", "名字", "名讳", "主角", "码头", "运河", "渡口", "棚下"}
    return dedupe_strings([item for item in candidates if item not in skip])


def extract_location_candidates(text: str) -> list[str]:
    pattern = r"([一-龥]{0,4}(?:码头|运河边|运河|乱葬岗|住处|棚下|棚屋|岸边|桥洞|渡口|河边|船舱|门口|窗边|屋里|巷口|街口))"
    matches = [str(item).strip() for item in re.findall(pattern, str(text or "")) if str(item).strip()]
    return dedupe_strings(matches)


def normalize_location_hint(candidate: str, anchors: list[str]) -> str:
    text = str(candidate or "").strip()
    if not text:
        return ""
    text = re.sub(r"^(?:继续保持|保持|继续|来到|回到|在|向|去|到|承接上一场继续保持)", "", text)
    if text == "运河":
        return "运河边"
    if text in {"棚下", "棚屋", "棚边"} and anchors:
        anchor = anchors[0]
        if anchor.endswith(text):
            return anchor
        return f"{anchor}{text}"
    return text


def build_story_state_bootstrap_config(task_text: str, chapter_state_text: str, locked_text: str) -> StoryStateBootstrapConfig:
    protagonist_candidates = []
    for source in (chapter_state_text, locked_text, task_text):
        protagonist_candidates.extend(extract_character_name_candidates(source))
    protagonist_name = protagonist_candidates[0] if protagonist_candidates else "主角"

    raw_location_candidates: list[str] = []
    task_and_state = f"{task_text}\n{chapter_state_text}"
    raw_location_candidates.extend(extract_location_candidates(task_and_state))
    if not raw_location_candidates:
        raw_location_candidates.extend(extract_location_candidates(locked_text))

    normalized_hints: list[str] = []
    major_anchors = [item for item in raw_location_candidates if item not in {"棚下", "棚屋", "棚边"}]
    for candidate in raw_location_candidates:
        normalized = normalize_location_hint(candidate, major_anchors or raw_location_candidates)
        if normalized and normalized not in normalized_hints:
            normalized_hints.append(normalized)

    return StoryStateBootstrapConfig(protagonist_name=protagonist_name, location_hints=normalized_hints)


def extract_explicit_relation_targets(text: str) -> list[str]:
    return dedupe_strings(
        [term for term in re.findall(r"[“\"]([^”\"]{1,12})[”\"]", text) if len(term.strip()) >= 2]
    )


def extract_item_candidates(text: str) -> list[str]:
    pattern = r"([一-龥]{1,8}(?:绳|线头|符|木牌|铜牌|玉佩|纸条|信|匣|盒|册|刀|钩|锥子|麻袋))"
    raw_matches = re.findall(pattern, text)
    normalized: list[str] = []
    canonical_suffixes = ["线头", "麻袋", "锥子", "木牌", "铜牌", "玉佩", "纸条", "匣", "盒", "册", "刀", "钩", "符", "绳", "信"]
    for item in raw_matches:
        name = item.strip()
        name = re.sub(r"^(?:他把|她把|把|将|又把|又捡起|捡起|拾起|摸出|取出|塞回|留住|留下)", "", name)
        if "的" in name:
            name = name.split("的")[-1]
        for suffix in canonical_suffixes:
            if name.endswith(suffix):
                if len(suffix) >= 2:
                    name = suffix
                break
        normalized.append(name)
    return dedupe_strings(normalized)


def looks_like_state_fragment(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    if len(value) > 24:
        return True
    if any(marker in value for marker in ("，", "。", "：", "；", "？", "！", "[", "]", "“", "”", "\"")):
        return True
    if re.search(r"(松开|拖到|塞回|捡起|拾起|看见|想起|走到|回到|放下|停住|留下|录入|混着|过码头)", value):
        return True
    return False


def clean_short_state_list(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or looks_like_state_fragment(text):
            continue
        cleaned.append(text)
    return dedupe_strings(cleaned)


def clean_known_fact_list(items: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        if text.startswith(("而是", "但是", "只是", "不是")):
            continue
        if re.search(r"(松开|拖到|塞回|捡起|拾起|看见|想起|走到|回到|放下|停住|留下|录入|混着|过码头)", text):
            continue
        if len(text) > 48:
            continue
        cleaned.append(text)
    return dedupe_strings(cleaned)


def infer_item_status(source_text: str) -> str:
    if any(marker in source_text for marker in ("贴身保留", "贴身", "腰间")):
        return "贴身保留"
    if any(marker in source_text for marker in ("袖口", "袖里", "袖中")):
        return "袖口暂留"
    if any(marker in source_text for marker in ("手里", "手上", "拿着", "留了下来")):
        return "暂时持有"
    return "状态待确认"


def infer_item_owner(source_text: str, config: StoryStateBootstrapConfig) -> str:
    protagonist_name = str(config.protagonist_name or "").strip()
    if protagonist_name and protagonist_name != "主角" and protagonist_name in source_text:
        return protagonist_name
    name_candidates = extract_character_name_candidates(source_text)
    if name_candidates:
        return name_candidates[0]
    return "待确认"


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


def infer_location(task_text: str, chapter_state_text: str, locked_text: str, existing_value: str, config: StoryStateBootstrapConfig) -> str:
    for hint in config.location_hints:
        if hint and hint not in {"棚下", "棚屋", "棚边"}:
            return hint

    combined = f"{task_text}\n{chapter_state_text}\n{locked_text}"
    dynamic_candidates = extract_location_candidates(combined)
    if dynamic_candidates:
        return normalize_location_hint(dynamic_candidates[0], dynamic_candidates[1:] or dynamic_candidates)
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
    if any(marker in combined for marker in ("放不下", "停顿", "牵住", "牵动", "名字", "名讳", "线索")):
        tags.append("被未解线索持续牵动")
    if any(marker in combined for marker in ("未形成明确行动", "未展开主动追查", "尚未升级成主动追查", "不升级为明确调查")):
        tags.append("尚未转为调查")
    return "、".join(dedupe_strings(tags)) or existing_value or "unknown"


def infer_active_goals(task_text: str, protagonist_bullets: list[str], existing_items: list[str], config: StoryStateBootstrapConfig) -> list[str]:
    goals = list(existing_items)
    if any(marker in task_text for marker in ("底层求活", "求活日常", "做活")):
        base_location = next((item for item in config.location_hints if item and item not in {"棚下", "棚屋", "棚边"}), "")
        if base_location:
            goals.append(f"维持日常求活与{base_location}做活")
        else:
            goals.append("维持日常求活")
    if any(marker in " ".join(protagonist_bullets) for marker in ("尚未形成明确调查", "尚未形成行动计划", "无法轻易放下")):
        goals.append("在不主动追查的前提下继续压住这条未解线索")
    return dedupe_strings(goals)


def infer_open_tensions(protagonist_bullets: list[str], existing_items: list[str]) -> list[str]:
    tensions = list(existing_items)
    for bullet in protagonist_bullets:
        if any(marker in bullet for marker in ("尚未", "无法", "放不下", "牵动", "不再只", "仍未")):
            tensions.append(bullet)
    return dedupe_strings(tensions)


def infer_revealed_secrets(chapter_sections: dict[str, list[str]], scene_stem: str, existing: list[SecretState]) -> list[SecretState]:
    results = list(existing)
    existing_descriptions = {item.description for item in existing}
    clue_lines = chapter_sections.get("已锁定线索", []) + chapter_sections.get("当前主角状态", [])
    index = len(results) + 1
    secret_markers = ("名字", "身份", "背面", "记住", "留下", "牵动", "秘密")
    for clue in clue_lines:
        if clue in existing_descriptions:
            continue
        if not any(marker in clue for marker in secret_markers) and not re.search(r"[“\"].+?[”\"]", clue):
            continue
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


def infer_items(
    chapter_sections: dict[str, list[str]],
    scene_stem: str,
    existing: list[ItemState],
    config: StoryStateBootstrapConfig,
    locked_text: str = "",
) -> list[ItemState]:
    existing_by_name = {item.name: item for item in existing}
    results = list(existing)
    next_index = len(existing_by_name) + 1
    source_lines = chapter_sections.get("已锁定线索", []) + chapter_sections.get("当前主角状态", [])
    source_lines.extend([line.strip() for line in str(locked_text or "").splitlines() if line.strip()])
    for line in source_lines:
        for name in extract_item_candidates(line):
            if looks_like_state_fragment(name):
                continue
            if name in existing_by_name:
                continue
            results.append(
                ItemState(
                    id=item_id(next_index),
                    name=name,
                    owner=infer_item_owner(line, config),
                    status=infer_item_status(line),
                    last_seen_in=scene_stem,
                    notes=line,
                )
            )
            existing_by_name[name] = results[-1]
            next_index += 1
    return results


def infer_relationship_deltas(chapter_sections: dict[str, list[str]], scene_stem: str, existing: list[RelationshipDelta], config: StoryStateBootstrapConfig) -> list[RelationshipDelta]:
    results = list(existing)
    relation_lines = chapter_sections.get("当前主角状态", []) + chapter_sections.get("已锁定线索", [])
    scene_candidates: list[tuple[str, str]] = []
    for line in relation_lines:
        if not any(marker in line for marker in ("影响", "牵动", "放不下", "记住", "无法轻易放下", "改变")):
            continue
        targets = [name for name in extract_explicit_relation_targets(line) if name != config.protagonist_name]
        if not targets:
            continue
        scene_candidates.append((targets[0], line))

    selected_by_target: dict[str, str] = {}
    for target, line in scene_candidates:
        selected_by_target[target] = line

    for target, line in selected_by_target.items():
        if any(item.target == target and item.delta == line for item in results):
            continue
        results.append(
            RelationshipDelta(
                id=relationship_id(len(results) + 1),
                source=config.protagonist_name,
                target=target,
                delta=line,
                introduced_in=scene_stem,
                status="active",
            )
        )
    return results


def infer_unresolved_promises(chapter_sections: dict[str, list[str]], scene_stem: str, existing: list[PromiseState]) -> list[PromiseState]:
    results = list(existing)
    existing_descriptions = {item.description for item in results}
    for text in chapter_sections.get("暂不展开的内容", []):
        if text in existing_descriptions:
            continue
        results.append(
            PromiseState(
                id=promise_id(len(results) + 1),
                description=text,
                introduced_in=scene_stem,
                expected_payoff_window=infer_future_window(scene_stem),
            )
        )
    return results


def build_story_state_patch(existing: StoryState, task_text: str, chapter_state_text: str, locked_text: str, locked_file: str) -> StoryState:
    scene_stem = scene_stem_from_locked_file(locked_file)
    chapter_sections = parse_markdown_sections(chapter_state_text)
    protagonist_bullets = chapter_sections.get("当前主角状态", [])
    protagonist = existing.characters.get("protagonist", CharacterState())
    config = build_story_state_bootstrap_config(task_text, chapter_state_text, locked_text)

    event_id = event_id_from_scene(scene_stem)
    recent_events = dedupe_strings(existing.timeline.recent_events + [event_id])

    patch = StoryState(
        timeline=TimelineState(
            current_book_time=infer_book_time(chapter_state_text, locked_text, existing.timeline.current_book_time),
            recent_events=recent_events,
        ),
        characters={
            "protagonist": CharacterState(
                location=infer_location(task_text, chapter_state_text, locked_text, protagonist.location, config),
                physical_state=summarize_physical_state(protagonist_bullets, locked_text, protagonist.physical_state),
                mental_state=summarize_mental_state(protagonist_bullets, locked_text, protagonist.mental_state),
                known_facts=dedupe_strings(protagonist.known_facts + chapter_sections.get("已锁定线索", [])),
                active_goals=infer_active_goals(task_text, protagonist_bullets, protagonist.active_goals, config),
                open_tensions=infer_open_tensions(protagonist_bullets, protagonist.open_tensions),
            )
        },
        unresolved_promises=infer_unresolved_promises(chapter_sections, scene_stem, existing.unresolved_promises),
        revealed_secrets=infer_revealed_secrets(chapter_sections, scene_stem, existing.revealed_secrets),
        items=infer_items(chapter_sections, scene_stem, existing.items, config, locked_text=locked_text),
        relationship_deltas=infer_relationship_deltas(chapter_sections, scene_stem, existing.relationship_deltas, config),
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
    return clean_story_state(merged)


def clean_story_state(state: StoryState) -> StoryState:
    invalid_target_prefixes = ("这种", "这个", "当前", "本场", "场景", "变化", "动作")
    cleaned_relationships: list[RelationshipDelta] = []
    seen_pairs: set[tuple[str, str]] = set()

    for item in state.relationship_deltas:
        target = item.target.strip()
        delta = item.delta.strip()
        if not target or any(target.startswith(prefix) for prefix in invalid_target_prefixes):
            continue
        key = (target, delta)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        cleaned_relationships.append(item)

    state.relationship_deltas = cleaned_relationships
    for character in state.characters.values():
        character.known_facts = clean_known_fact_list(character.known_facts)
        character.active_goals = clean_short_state_list(character.active_goals)
        character.open_tensions = clean_short_state_list(character.open_tensions)

    cleaned_items: list[ItemState] = []
    seen_item_names: set[str] = set()
    for item in state.items:
        item.name = str(item.name or "").strip()
        item.notes = str(item.notes or "").strip()
        if looks_like_state_fragment(item.name):
            continue
        if item.name in seen_item_names:
            continue
        seen_item_names.add(item.name)
        cleaned_items.append(item)
    state.items = cleaned_items

    cleaned_promises: list[PromiseState] = []
    for item in state.unresolved_promises:
        item.description = str(item.description or "").strip()
        if not item.description or len(item.description) > 40:
            continue
        cleaned_promises.append(item)
    state.unresolved_promises = cleaned_promises
    return state


def build_character_patch(existing: CharacterState, merged: CharacterState) -> CharacterStatePatch:
    return CharacterStatePatch(
        location=merged.location if merged.location != existing.location else None,
        physical_state=merged.physical_state if merged.physical_state != existing.physical_state else None,
        mental_state=merged.mental_state if merged.mental_state != existing.mental_state else None,
        known_facts_to_add=[item for item in merged.known_facts if item not in existing.known_facts],
        active_goals_to_add=[item for item in merged.active_goals if item not in existing.active_goals],
        open_tensions_to_add=[item for item in merged.open_tensions if item not in existing.open_tensions],
    )


def build_story_state_patch_proposal(
    existing: StoryState,
    merged: StoryState,
    task_text: str,
    locked_file: str,
) -> StoryStatePatchProposal:
    task_id = extract_markdown_field(task_text, "task_id") or scene_stem_from_locked_file(locked_file)
    character_updates: dict[str, CharacterStatePatch] = {}
    for character_key, merged_character in merged.characters.items():
        existing_character = existing.characters.get(character_key, CharacterState())
        patch = build_character_patch(existing_character, merged_character)
        if model_to_dict(patch) != model_to_dict(CharacterStatePatch()):
            character_updates[character_key] = patch

    timeline_updates: dict[str, Any] = {}
    if merged.timeline.current_book_time != existing.timeline.current_book_time:
        timeline_updates["current_book_time"] = merged.timeline.current_book_time
    recent_events_to_add = [item for item in merged.timeline.recent_events if item not in existing.timeline.recent_events]
    if recent_events_to_add:
        timeline_updates["recent_events_to_add"] = recent_events_to_add

    unresolved_promises_to_add = [item for item in merged.unresolved_promises if all(item.id != old.id for old in existing.unresolved_promises)]
    revealed_secrets_to_add = [item for item in merged.revealed_secrets if all(item.id != old.id for old in existing.revealed_secrets)]
    relationship_deltas_to_add = [item for item in merged.relationship_deltas if all(item.id != old.id for old in existing.relationship_deltas)]

    existing_items_by_id = {item.id: item for item in existing.items}
    item_updates: list[ItemState] = []
    for item in merged.items:
        previous = existing_items_by_id.get(item.id)
        if previous is None or model_to_dict(previous) != model_to_dict(item):
            item_updates.append(item)

    reasons = []
    if timeline_updates:
        reasons.append("同步时间线与最近事件")
    if character_updates:
        reasons.append("补入主角位置、身心状态与当前张力")
    if unresolved_promises_to_add:
        reasons.append("记录尚未兑现的章节承诺")
    if revealed_secrets_to_add:
        reasons.append("记录已显性暴露的关键信息")
    if item_updates:
        reasons.append("同步物品归属与状态")
    if relationship_deltas_to_add:
        reasons.append("同步人物关系张力变化")

    return StoryStatePatchProposal(
        task_id=task_id,
        locked_file=locked_file,
        based_on_state=STORY_STATE_REL_PATH,
        timeline_updates=timeline_updates,
        character_updates=character_updates,
        unresolved_promises_to_add=unresolved_promises_to_add,
        revealed_secrets_to_add=revealed_secrets_to_add,
        item_updates=item_updates,
        relationship_deltas_to_add=relationship_deltas_to_add,
        decision_reason="；".join(reasons) or "本次 lock 未产生新的结构化状态增量。",
    )


def build_story_state_patch_proposal_path(scene_stem: str) -> str:
    return f"{STORY_STATE_PROPOSAL_DIR}/{scene_stem}_story_state_patch.json"


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


def list_locked_chapter_files(root: Path, locked_dir: str = "03_locked/chapters") -> list[str]:
    path = root / locked_dir
    if not path.exists():
        return []
    files = [item.relative_to(root).as_posix() for item in path.glob("*.md") if item.is_file()]
    files.sort(key=lambda item: scene_sort_key_from_name(Path(item).stem))
    return files


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
    proposal = build_story_state_patch_proposal(previous_state, merged, task_text, locked_file)
    proposal_rel_path = build_story_state_patch_proposal_path(scene_stem)
    proposal.save(root / proposal_rel_path)
    story_state_rel_path, diff_rel_path, snapshot_rel_path = save_story_state_files(root, merged, scene_stem, previous_state)
    return {
        "story_state_file": story_state_rel_path,
        "story_state_patch_file": proposal_rel_path,
        "story_state_diff_file": diff_rel_path,
        "story_state_snapshot_file": snapshot_rel_path,
    }


def rebuild_story_state_from_locked(root: Path, locked_dir: str = "03_locked/chapters") -> dict[str, Any]:
    clear_story_state_outputs(root)

    processed_scenes: list[dict[str, str | None]] = []
    outputs: dict[str, str] | None = None
    locked_files = list_locked_chapter_files(root, locked_dir=locked_dir)

    for locked_file in locked_files:
        scene_stem = scene_stem_from_locked_file(locked_file)
        task_text, task_file = resolve_task_text_for_scene(root, scene_stem, locked_file)
        chapter_state_path = extract_markdown_field(task_text, "chapter_state") or infer_chapter_state_path_from_scene(scene_stem)
        outputs = update_story_state_on_lock(
            root,
            task_text,
            locked_file,
            chapter_state_path=chapter_state_path,
        )
        processed_scenes.append(
            {
                "scene": scene_stem,
                "locked_file": locked_file,
                "task_file": task_file,
                "chapter_state": chapter_state_path,
            }
        )

    return {
        "processed_scenes": processed_scenes,
        "final_story_state_file": outputs["story_state_file"] if outputs else STORY_STATE_REL_PATH,
        "scene_count": len(processed_scenes),
    }
