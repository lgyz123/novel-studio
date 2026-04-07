import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


TRACKER_DIR = "03_locked/state/trackers"
TRACKER_PROPOSAL_DIR = "02_working/canon_updates"

SCENE_FUNCTION_LABELS = [
    "发现线索",
    "引入阻力",
    "触发调查",
    "揭示关系",
    "制造错误判断",
    "引发后果",
    "提高风险",
    "扩展世界信息",
    "过渡/氛围",
]

DISCOVERY_MARKERS = ["发现", "认出", "确认", "看到", "摸到", "捡到", "拾到", "写着", "露出", "原来", "竟是"]
DECISION_MARKERS = ["决定", "收起", "藏起", "记下", "转向", "询问", "隐瞒", "回去", "停止", "撒谎", "跟踪", "取走", "放弃", "塞进", "挪开", "压回"]
CONSEQUENCE_MARKERS = ["结果", "于是", "随后", "接着", "只好", "导致", "没能", "暴露", "惹来", "逼得"]
RISK_MARKERS = ["差点", "险些", "麻烦", "暴露", "不敢", "更难", "盯上", "惹来", "失手"]
WORLD_MARKERS = ["衙门", "规矩", "行当", "河道", "码头规矩", "停尸", "收尸行"]
RELATIONSHIP_MARKERS = ["名字", "旧识", "记得", "认得", "她曾", "她总", "两个人", "一起"]
MISJUDGMENT_MARKERS = ["还当", "误以为", "只当", "本以为", "认错", "看走眼"]
INVESTIGATION_MARKERS = ["追问", "打听", "调查", "跟踪", "查清", "问清", "探查"]
TRANSITION_MARKERS = ["疲惫", "寒气", "气味", "风", "冷", "潮气", "想起", "发怔", "联想"]

GENERIC_FAMILIARITY_MARKERS = ["总爱", "总会", "从前", "以前", "那年", "一起", "替他", "替她", "并肩", "笑着", "住在"]
CARRIED_ARTIFACT_MARKERS = ["怀里", "袖里", "袖中", "贴身", "腰间", "身上", "怀中", "揣着", "带着", "塞回", "摸出来"]
LOCATION_CHANGE_MARKERS = ["放在", "藏在", "塞进", "挂在", "留在", "压在"]

ARTIFACT_PATTERNS = [
    re.compile(r"([\u4e00-\u9fff]{1,4}(?:绳|符|钱|铃|牌|佩|匣|盒|袋|册|刀|钩|线头|木牌|纸条))"),
]
SMELL_PATTERNS = [
    re.compile(r"([\u4e00-\u9fff]{1,4}(?:气味|味|臭|腥气|潮气|霉气))"),
]
BODY_SENSATION_PATTERNS = [
    re.compile(r"((?:喉头|喉结|胸口|后颈|指节|胃里|腕骨|肩头|眼眶|鼻腔|背脊|心口)[\u4e00-\u9fff]{0,3})"),
]
ENVIRONMENT_PATTERNS = [
    re.compile(r"([\u4e00-\u9fff]{1,4}(?:窝棚|棚屋|岸边|桥洞|河道|码头|船舱|门口|窗边|屋里|渡口))"),
]
IDENTITY_PATTERNS = [
    re.compile(r"(?:名字|字样|写着|刻着|背面是)[“\"『「]?([\u4e00-\u9fff]{1,4})[”\"』」]?"),
]
MEMORY_TRIGGER_PATTERNS = [
    re.compile(r"((?:想起|记起|梦见|闻见|看见)[\u4e00-\u9fff]{1,6})"),
]


class MotifEntry(BaseModel):
    motif_id: str
    category: str
    label: str
    narrative_functions: list[str] = Field(default_factory=list)
    status: str = "active"
    recent_scene_ids: list[str] = Field(default_factory=list)
    recent_usage_count: int = 0
    allow_next_scene: bool = True
    only_if_new_function: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MotifEntry":
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls.parse_obj(data)


class ChapterMotifTracker(BaseModel):
    chapter_id: str
    active_motifs: list[MotifEntry] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChapterMotifTracker":
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls.parse_obj(data)


class RevelationTracker(BaseModel):
    chapter_id: str
    confirmed_facts: list[str] = Field(default_factory=list)
    suspected_facts: list[str] = Field(default_factory=list)
    unrevealed_facts: list[str] = Field(default_factory=list)
    forbidden_premature_reveals: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RevelationTracker":
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls.parse_obj(data)


class ArtifactStateItem(BaseModel):
    item_id: str
    label: str
    holder: str = "待确认"
    location: str = "待确认"
    significance_level: str = "medium"
    last_changed_scene: str = ""

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactStateItem":
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls.parse_obj(data)


class ArtifactState(BaseModel):
    chapter_id: str
    items: list[ArtifactStateItem] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactState":
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls.parse_obj(data)


class ChapterProgress(BaseModel):
    chapter_id: str
    chapter_goal: str = ""
    completed_scene_functions: list[str] = Field(default_factory=list)
    remaining_scene_functions: list[str] = Field(default_factory=list)
    consecutive_transition_scene_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChapterProgress":
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls.parse_obj(data)


class TrackerUpdateProposal(BaseModel):
    motif_updates: list[dict[str, Any]] = Field(default_factory=list)
    revelation_updates: list[dict[str, Any]] = Field(default_factory=list)
    artifact_state_hints: list[dict[str, Any]] = Field(default_factory=list)
    progress_updates: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


def normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def safe_load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_markdown_field(task_text: str, field_name: str) -> str | None:
    pattern = rf"(?ms)^#\s*{re.escape(field_name)}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, str(task_text or ""))
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


def parse_markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_heading = ""
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            current_heading = line[3:].strip()
            sections[current_heading] = []
            continue
        if current_heading:
            sections[current_heading].append(raw_line.rstrip())
    return sections


def extract_bullets_from_section(section_lines: list[str]) -> list[str]:
    bullets: list[str] = []
    for raw_line in section_lines:
        stripped = raw_line.strip()
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if value and value not in bullets:
                bullets.append(value)
    return bullets


def chapter_id_from_locked_file(locked_file: str) -> str:
    match = re.search(r"(ch\d+)_scene\d+", Path(locked_file).stem)
    if not match:
        raise ValueError(f"无法从 locked 文件提取 chapter_id：{locked_file}")
    return match.group(1)


def scene_id_from_locked_file(locked_file: str) -> str:
    match = re.search(r"(ch\d+_scene\d+)", Path(locked_file).stem)
    if not match:
        return Path(locked_file).stem
    return match.group(1)


def tracker_file_paths(chapter_id: str) -> dict[str, str]:
    return {
        "chapter_motif_tracker": f"{TRACKER_DIR}/{chapter_id}_chapter_motif_tracker.json",
        "revelation_tracker": f"{TRACKER_DIR}/{chapter_id}_revelation_tracker.json",
        "artifact_state": f"{TRACKER_DIR}/{chapter_id}_artifact_state.json",
        "chapter_progress": f"{TRACKER_DIR}/{chapter_id}_chapter_progress.json",
    }


def classify_scene_function(scene_text: str) -> str:
    text = str(scene_text or "")
    if any(marker in text for marker in INVESTIGATION_MARKERS):
        return "触发调查"
    if any(marker in text for marker in MISJUDGMENT_MARKERS):
        return "制造错误判断"
    if any(marker in text for marker in DISCOVERY_MARKERS):
        return "发现线索"
    if any(marker in text for marker in CONSEQUENCE_MARKERS):
        return "引发后果"
    if any(marker in text for marker in RISK_MARKERS):
        return "提高风险"
    if any(marker in text for marker in WORLD_MARKERS):
        return "扩展世界信息"
    if any(marker in text for marker in RELATIONSHIP_MARKERS) and any(marker in text for marker in DECISION_MARKERS):
        return "揭示关系"
    if any(marker in text for marker in DECISION_MARKERS):
        return "引入阻力"
    return "过渡/氛围"


def list_locked_chapter_files(root: Path, chapter_id: str, upto_scene_id: str | None = None) -> list[Path]:
    chapter_dir = root / "03_locked/chapters"
    files: list[tuple[int, Path]] = []
    max_scene_number: int | None = None
    if upto_scene_id:
        match = re.search(rf"{re.escape(chapter_id)}_scene(\d+)", upto_scene_id)
        if match:
            max_scene_number = int(match.group(1))
    if not chapter_dir.exists():
        return []
    for path in chapter_dir.glob(f"{chapter_id}_scene*.md"):
        match = re.search(rf"{re.escape(chapter_id)}_scene(\d+)", path.stem)
        if not match:
            continue
        scene_number = int(match.group(1))
        if max_scene_number is not None and scene_number > max_scene_number:
            continue
        files.append((scene_number, path))
    return [item[1] for item in sorted(files, key=lambda item: item[0])]


def count_consecutive_transition_scenes(scene_texts: list[str]) -> int:
    count = 0
    for scene_text in reversed(scene_texts):
        if classify_scene_function(scene_text) == "过渡/氛围":
            count += 1
            continue
        break
    return count


def slugify_label(label: str) -> str:
    text = re.sub(r"\s+", "_", str(label).strip().lower())
    text = re.sub(r"[^a-z0-9_\-\u4e00-\u9fff]", "", text)
    return text or "motif"


def classify_motif_category(label: str) -> str:
    if any(pattern.search(label) for pattern in ARTIFACT_PATTERNS):
        return "artifact_motif"
    if any(pattern.search(label) for pattern in SMELL_PATTERNS):
        return "smell_motif"
    if any(pattern.search(label) for pattern in BODY_SENSATION_PATTERNS):
        return "body_sensation_motif"
    if any(pattern.search(label) for pattern in ENVIRONMENT_PATTERNS):
        return "environment_motif"
    if any(pattern.search(label) for pattern in IDENTITY_PATTERNS):
        return "identity_motif"
    if any(pattern.search(label) for pattern in MEMORY_TRIGGER_PATTERNS):
        return "memory_trigger_motif"
    return "environment_motif"


def extract_candidate_motifs_from_text(text: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    pattern_groups = [
        ("artifact_motif", ARTIFACT_PATTERNS),
        ("smell_motif", SMELL_PATTERNS),
        ("body_sensation_motif", BODY_SENSATION_PATTERNS),
        ("environment_motif", ENVIRONMENT_PATTERNS),
        ("identity_motif", IDENTITY_PATTERNS),
        ("memory_trigger_motif", MEMORY_TRIGGER_PATTERNS),
    ]
    for category, patterns in pattern_groups:
        for pattern in patterns:
            for match in pattern.findall(str(text or "")):
                label = match if isinstance(match, str) else match[0]
                label = str(label).strip("“”‘’\"' ，。；：:、")
                if len(label) < 2:
                    continue
                item = (category, label)
                if item not in candidates:
                    candidates.append(item)
    return candidates


def bootstrap_chapter_motif_tracker(root: Path, chapter_id: str, upto_scene_id: str | None = None) -> ChapterMotifTracker:
    locked_files = list_locked_chapter_files(root, chapter_id, upto_scene_id=upto_scene_id)
    recent_files = locked_files[-3:]
    motif_map: dict[str, MotifEntry] = {}
    for path in recent_files:
        scene_id = scene_id_from_locked_file(path.as_posix())
        scene_text = path.read_text(encoding="utf-8") if path.exists() else ""
        for category, label in extract_candidate_motifs_from_text(scene_text):
            motif_id = f"{category}_{slugify_label(label)}"
            entry = motif_map.get(motif_id)
            if entry is None:
                entry = MotifEntry(
                    motif_id=motif_id,
                    category=category,
                    label=label,
                    narrative_functions=[classify_scene_function(scene_text)],
                    status="active",
                    recent_scene_ids=[scene_id],
                    recent_usage_count=1,
                    allow_next_scene=True,
                    only_if_new_function=False,
                    notes="bootstrap_from_recent_locked_scenes",
                )
                motif_map[motif_id] = entry
            else:
                if scene_id not in entry.recent_scene_ids:
                    entry.recent_scene_ids.append(scene_id)
                    entry.recent_usage_count += 1
                scene_function = classify_scene_function(scene_text)
                if scene_function not in entry.narrative_functions:
                    entry.narrative_functions.append(scene_function)
    for entry in motif_map.values():
        entry.allow_next_scene = entry.recent_usage_count < 2
        entry.only_if_new_function = entry.recent_usage_count >= 2
    return ChapterMotifTracker(chapter_id=chapter_id, active_motifs=list(motif_map.values()))


def bootstrap_revelation_tracker(chapter_id: str, chapter_state_text: str, story_state: dict[str, Any] | None) -> RevelationTracker:
    story_state = story_state or {}
    sections = parse_markdown_sections(chapter_state_text)
    protagonist = ((story_state.get("characters") or {}).get("protagonist") or {})
    confirmed_facts = normalize_string_list(protagonist.get("known_facts", []))
    suspected_facts = normalize_string_list(protagonist.get("open_tensions", []))
    unrevealed_facts = normalize_string_list(extract_bullets_from_section(sections.get("已锁定线索", [])))
    forbidden_premature_reveals = normalize_string_list(extract_bullets_from_section(sections.get("暂不展开的内容", [])))
    for promise in story_state.get("unresolved_promises", []) if isinstance(story_state.get("unresolved_promises"), list) else []:
        description = str(promise.get("description") or "").strip()
        if description and description not in forbidden_premature_reveals:
            forbidden_premature_reveals.append(description)
    return RevelationTracker(
        chapter_id=chapter_id,
        confirmed_facts=confirmed_facts[:12],
        suspected_facts=suspected_facts[:12],
        unrevealed_facts=unrevealed_facts[:12],
        forbidden_premature_reveals=forbidden_premature_reveals[:12],
    )


def bootstrap_artifact_state(chapter_id: str, story_state: dict[str, Any] | None) -> ArtifactState:
    story_state = story_state or {}
    items = story_state.get("items", []) if isinstance(story_state.get("items"), list) else []
    tracker_items: list[ArtifactStateItem] = []
    for index, item in enumerate(items, start=1):
        tracker_items.append(
            ArtifactStateItem(
                item_id=str(item.get("id") or f"artifact_{index:03d}").strip(),
                label=str(item.get("name") or item.get("label") or f"artifact_{index:03d}").strip(),
                holder=str(item.get("owner") or "待确认").strip() or "待确认",
                location=str(item.get("status") or item.get("notes") or "待确认").strip() or "待确认",
                significance_level="medium",
                last_changed_scene=str(item.get("last_seen_in") or "").strip(),
            )
        )
    return ArtifactState(chapter_id=chapter_id, items=tracker_items)


def bootstrap_chapter_progress(root: Path, chapter_id: str, chapter_state_text: str, story_state: dict[str, Any] | None, upto_scene_id: str | None = None) -> ChapterProgress:
    locked_files = list_locked_chapter_files(root, chapter_id, upto_scene_id=upto_scene_id)
    scene_texts = [path.read_text(encoding="utf-8") for path in locked_files if path.exists()]
    completed = [f"{scene_id_from_locked_file(path.as_posix())}: {classify_scene_function(text)}" for path, text in zip(locked_files, scene_texts)]
    completed_labels = [classify_scene_function(text) for text in scene_texts if classify_scene_function(text) != "过渡/氛围"]
    sections = parse_markdown_sections(chapter_state_text)
    chapter_goal_candidates = extract_bullets_from_section(sections.get("scene03 建议目标", []))
    protagonist_goal = normalize_string_list((((story_state or {}).get("characters") or {}).get("protagonist") or {}).get("active_goals", []))
    if not chapter_goal_candidates:
        chapter_goal_candidates = protagonist_goal[:2]
    remaining = [label for label in SCENE_FUNCTION_LABELS if label not in completed_labels and label != "过渡/氛围"]
    consecutive = count_consecutive_transition_scenes(scene_texts)
    if consecutive >= 2:
        forced = [item for item in ["发现线索", "引入阻力", "触发调查", "引发后果"] if item in remaining]
        remaining = forced + [item for item in remaining if item not in forced]
    return ChapterProgress(
        chapter_id=chapter_id,
        chapter_goal="；".join(chapter_goal_candidates[:2]) if chapter_goal_candidates else "以 scene function、信息增量、决策变化、状态转移推进本章。",
        completed_scene_functions=completed[-8:],
        remaining_scene_functions=remaining[:8],
        consecutive_transition_scene_count=consecutive,
    )


def load_tracker_bundle(root: Path, chapter_id: str, chapter_state_text: str = "", story_state: dict[str, Any] | None = None, upto_scene_id: str | None = None) -> dict[str, Any]:
    paths = tracker_file_paths(chapter_id)
    motif_data = safe_load_json(root / paths["chapter_motif_tracker"])
    revelation_data = safe_load_json(root / paths["revelation_tracker"])
    artifact_data = safe_load_json(root / paths["artifact_state"])
    progress_data = safe_load_json(root / paths["chapter_progress"])

    chapter_motif_tracker = ChapterMotifTracker.from_dict(motif_data) if motif_data else bootstrap_chapter_motif_tracker(root, chapter_id, upto_scene_id=upto_scene_id)
    if not chapter_motif_tracker.active_motifs:
        chapter_motif_tracker = bootstrap_chapter_motif_tracker(root, chapter_id, upto_scene_id=upto_scene_id)
    revelation_tracker = RevelationTracker.from_dict(revelation_data) if revelation_data else bootstrap_revelation_tracker(chapter_id, chapter_state_text, story_state)
    artifact_state = ArtifactState.from_dict(artifact_data) if artifact_data else bootstrap_artifact_state(chapter_id, story_state)
    chapter_progress = ChapterProgress.from_dict(progress_data) if progress_data else bootstrap_chapter_progress(root, chapter_id, chapter_state_text, story_state, upto_scene_id=upto_scene_id)

    return {
        "chapter_motif_tracker": chapter_motif_tracker.to_dict(),
        "revelation_tracker": revelation_tracker.to_dict(),
        "artifact_state": artifact_state.to_dict(),
        "chapter_progress": chapter_progress.to_dict(),
        "tracker_files": paths,
    }


def extract_scene_id_from_task_or_locked(task_text: str = "", locked_file: str = "") -> str:
    task_id = extract_markdown_field(task_text, "task_id")
    if task_id:
        match = re.search(r"(ch\d+_scene\d+)", task_id)
        if match:
            return match.group(1)
    if locked_file:
        return scene_id_from_locked_file(locked_file)
    output_target = extract_markdown_field(task_text, "output_target") or ""
    match = re.search(r"(ch\d+_scene\d+)", output_target)
    return match.group(1) if match else "unknown_scene"


def chapter_id_from_task_or_locked(task_text: str = "", locked_file: str = "") -> str:
    scene_id = extract_scene_id_from_task_or_locked(task_text, locked_file)
    match = re.search(r"(ch\d+)_scene\d+", scene_id)
    if match:
        return match.group(1)
    chapter_state_path = extract_markdown_field(task_text, "chapter_state") or ""
    match = re.search(r"(ch\d+)", chapter_state_path)
    if match:
        return match.group(1)
    raise ValueError("无法从 task/locked_file 推断 chapter_id")


def motif_entries_in_text(text: str, chapter_motif_tracker: dict[str, Any]) -> list[dict[str, Any]]:
    active_motifs = chapter_motif_tracker.get("active_motifs", []) if isinstance(chapter_motif_tracker, dict) else []
    matches: list[dict[str, Any]] = []
    for entry in active_motifs:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        if label and label in text:
            matches.append(entry)
    return matches


def build_tracker_update_proposal_from_plan(plan: dict[str, Any], tracker_bundle: dict[str, Any]) -> dict[str, Any]:
    scene_function = str(plan.get("scene_function") or "").strip()
    scene_purpose = str(plan.get("scene_purpose") or "").strip()
    required_information_gain = normalize_string_list(plan.get("required_information_gain", []))
    required_state_change = normalize_string_list(plan.get("required_state_change", []))
    motif_budget = plan.get("motif_budget_for_scene") if isinstance(plan.get("motif_budget_for_scene"), dict) else {}

    motif_updates: list[dict[str, Any]] = []
    chapter_motif_tracker = tracker_bundle.get("chapter_motif_tracker", {}) if isinstance(tracker_bundle, dict) else {}
    active_motifs = chapter_motif_tracker.get("active_motifs", []) if isinstance(chapter_motif_tracker, dict) else []
    for entry in active_motifs:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        motif_id = str(entry.get("motif_id") or "").strip()
        if not label or not motif_id:
            continue
        if label in normalize_string_list(motif_budget.get("banned_motifs", [])):
            motif_updates.append(
                {
                    "op": "add_or_update",
                    "motif_id": motif_id,
                    "category": entry.get("category"),
                    "label": label,
                    "narrative_functions": normalize_string_list(entry.get("narrative_functions", [])) + ([scene_function] if scene_function else []),
                    "allow_next_scene": False,
                    "only_if_new_function": True,
                    "reason": "recently repeated without enough function change",
                }
            )

    revelation_updates = [{"op": "anticipate", "fact": item, "reason": scene_purpose or scene_function} for item in required_information_gain[:2]]
    artifact_state_hints = [{"op": "anticipate_change", "state_change": item, "reason": scene_function} for item in required_state_change]
    progress_updates = [{"op": "plan_scene_function", "scene_function": scene_function, "scene_purpose": scene_purpose}]

    return TrackerUpdateProposal(
        motif_updates=motif_updates,
        revelation_updates=revelation_updates,
        artifact_state_hints=artifact_state_hints,
        progress_updates=progress_updates,
    ).to_dict()


def extract_fact_tokens(fact: str) -> list[str]:
    tokens = re.findall(r"[\u4e00-\u9fff]{2,6}", str(fact or ""))
    stopwords = {"当前", "不得", "不要", "揭示", "身份", "状态", "变化", "线索", "内容", "继续", "已经", "因为"}
    return [token for token in tokens if token not in stopwords]


def detect_forbidden_reveal_violations(draft_text: str, revelation_tracker: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    forbidden = revelation_tracker.get("forbidden_premature_reveals", []) if isinstance(revelation_tracker, dict) else []
    for fact in forbidden:
        fact_text = str(fact).strip()
        if not fact_text:
            continue
        tokens = extract_fact_tokens(fact_text)
        if tokens and any(token in draft_text for token in tokens) and any(marker in draft_text for marker in GENERIC_FAMILIARITY_MARKERS):
            violations.append(f"禁止提前揭示的内容“{fact_text}”在正文中出现了过度熟识化表达。")
    return violations[:3]


def detect_artifact_state_conflicts(draft_text: str, artifact_state: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
    for item in artifact_state.get("items", []) if isinstance(artifact_state, dict) else []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        holder = str(item.get("holder") or "").strip()
        location = str(item.get("location") or "").strip()
        if not label or label not in draft_text:
            continue
        if holder and holder not in {"待确认", ""} and holder not in draft_text and any(marker in draft_text for marker in CARRIED_ARTIFACT_MARKERS):
            conflicts.append(f"物件“{label}”当前持有者应为“{holder}”，但正文写法与现有 artifact_state 不一致。")
        if location and location not in {"待确认", ""} and location not in draft_text and any(marker in draft_text for marker in LOCATION_CHANGE_MARKERS + CARRIED_ARTIFACT_MARKERS):
            conflicts.append(f"物件“{label}”当前所在位置应为“{location}”，但正文写法与现有 artifact_state 不一致。")
    return conflicts[:3]


def merge_scene_ids(existing: list[str], scene_id: str) -> list[str]:
    merged = [item for item in existing if item != scene_id]
    merged.append(scene_id)
    return merged[-3:]


def derive_actual_tracker_updates(root: Path, task_text: str, locked_file: str, reviewer_result: dict[str, Any], tracker_bundle: dict[str, Any]) -> dict[str, Any]:
    chapter_id = chapter_id_from_task_or_locked(task_text, locked_file)
    scene_id = scene_id_from_locked_file(locked_file)
    locked_text = (root / locked_file).read_text(encoding="utf-8") if (root / locked_file).exists() else ""

    chapter_motif_tracker = ChapterMotifTracker.from_dict(tracker_bundle.get("chapter_motif_tracker", {"chapter_id": chapter_id}))
    revelation_tracker = RevelationTracker.from_dict(tracker_bundle.get("revelation_tracker", {"chapter_id": chapter_id}))
    artifact_state = ArtifactState.from_dict(tracker_bundle.get("artifact_state", {"chapter_id": chapter_id}))
    chapter_progress = ChapterProgress.from_dict(tracker_bundle.get("chapter_progress", {"chapter_id": chapter_id}))

    motif_map = {entry.motif_id: entry for entry in chapter_motif_tracker.active_motifs}
    reviewer_scene_function = str(extract_markdown_field(task_text, "scene_function") or classify_scene_function(locked_text)).strip() or classify_scene_function(locked_text)
    for category, label in extract_candidate_motifs_from_text(locked_text):
        motif_id = f"{category}_{slugify_label(label)}"
        entry = motif_map.get(motif_id)
        if entry is None:
            entry = MotifEntry(motif_id=motif_id, category=category, label=label, narrative_functions=[reviewer_scene_function], recent_scene_ids=[scene_id], recent_usage_count=1)
            motif_map[motif_id] = entry
        else:
            entry.recent_scene_ids = merge_scene_ids(entry.recent_scene_ids, scene_id)
            entry.recent_usage_count = min(max(entry.recent_usage_count + 1, len(entry.recent_scene_ids)), 99)
            if reviewer_scene_function and reviewer_scene_function not in entry.narrative_functions:
                entry.narrative_functions.append(reviewer_scene_function)
        repeated_motifs = normalize_string_list((reviewer_result.get("motif_redundancy") or {}).get("repeated_motifs", []))
        if label in repeated_motifs and not (reviewer_result.get("motif_redundancy") or {}).get("repetition_has_new_function", True):
            entry.allow_next_scene = False
            entry.only_if_new_function = True
            entry.notes = "locked_scene_repeated_without_new_function"
        else:
            entry.allow_next_scene = entry.recent_usage_count < 2
            entry.only_if_new_function = entry.recent_usage_count >= 2
    chapter_motif_tracker.active_motifs = list(motif_map.values())

    new_facts = normalize_string_list((reviewer_result.get("information_gain") or {}).get("new_information_items", []))
    revelation_tracker.confirmed_facts = normalize_string_list(revelation_tracker.confirmed_facts + new_facts)
    revelation_tracker.suspected_facts = [item for item in revelation_tracker.suspected_facts if item not in new_facts]
    revelation_tracker.unrevealed_facts = [item for item in revelation_tracker.unrevealed_facts if item not in new_facts]

    artifact_map = {item.item_id: item for item in artifact_state.items}
    for category, label in extract_candidate_motifs_from_text(locked_text):
        if category != "artifact_motif":
            continue
        item_id = f"artifact_{slugify_label(label)}"
        item = artifact_map.get(item_id)
        if item is None:
            item = ArtifactStateItem(item_id=item_id, label=label, last_changed_scene=scene_id)
            artifact_map[item_id] = item
        item.last_changed_scene = scene_id
        if any(marker in locked_text for marker in CARRIED_ARTIFACT_MARKERS):
            item.location = "随身携带"
            item.holder = "主角"
        for marker in LOCATION_CHANGE_MARKERS:
            match = re.search(rf"{re.escape(label)}.{{0,8}}{re.escape(marker)}([^，。；\n]+)", locked_text)
            if match:
                item.location = match.group(1).strip()
                break
    artifact_state.items = list(artifact_map.values())

    completed = [item for item in chapter_progress.completed_scene_functions if not item.startswith(f"{scene_id}: ")]
    completed.append(f"{scene_id}: {reviewer_scene_function}")
    chapter_progress.completed_scene_functions = completed[-8:]
    remaining = [item for item in chapter_progress.remaining_scene_functions if item != reviewer_scene_function]
    chapter_progress.remaining_scene_functions = remaining
    chapter_progress.consecutive_transition_scene_count = chapter_progress.consecutive_transition_scene_count + 1 if reviewer_scene_function == "过渡/氛围" else 0

    return {
        "chapter_motif_tracker": chapter_motif_tracker.to_dict(),
        "revelation_tracker": revelation_tracker.to_dict(),
        "artifact_state": artifact_state.to_dict(),
        "chapter_progress": chapter_progress.to_dict(),
    }


def save_tracker_bundle(root: Path, bundle: dict[str, Any], chapter_id: str) -> dict[str, str]:
    paths = tracker_file_paths(chapter_id)
    outputs: dict[str, str] = {}
    for key, rel_path in paths.items():
        data = bundle.get(key)
        if not isinstance(data, dict):
            continue
        save_json(root / rel_path, data)
        outputs[f"{key}_file"] = rel_path
    return outputs


def update_trackers_on_lock(root: Path, task_text: str, locked_file: str, reviewer_result: dict[str, Any]) -> dict[str, str]:
    chapter_id = chapter_id_from_task_or_locked(task_text, locked_file)
    chapter_state_path = extract_markdown_field(task_text, "chapter_state")
    chapter_state_text = (root / chapter_state_path).read_text(encoding="utf-8") if chapter_state_path and (root / chapter_state_path).exists() else ""
    story_state_path = root / "03_locked/state/story_state.json"
    story_state = safe_load_json(story_state_path)
    tracker_bundle = load_tracker_bundle(root, chapter_id, chapter_state_text=chapter_state_text, story_state=story_state, upto_scene_id=scene_id_from_locked_file(locked_file))
    updated_bundle = derive_actual_tracker_updates(root, task_text, locked_file, reviewer_result, tracker_bundle)
    return save_tracker_bundle(root, updated_bundle, chapter_id)
