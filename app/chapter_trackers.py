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

GENERIC_FAMILIARITY_MARKERS = ["总爱", "总会", "从前", "以前", "那年", "一起", "替他", "替她", "并肩", "笑着", "住在", "相识", "旧识", "熟悉"]
CARRIED_ARTIFACT_MARKERS = ["怀里", "袖里", "袖中", "贴身", "腰间", "身上", "怀中", "揣着", "带着", "塞回", "摸出来"]
LOCATION_CHANGE_MARKERS = ["放在", "藏在", "塞进", "挂在", "留在", "压在"]
PROTAGONIST_HOLDER_ALIASES = {"主角", "孟浮灯"}
BODY_CARRY_LOCATION_MARKERS = ["贴着胸口", "胸前", "里襟", "最内侧", "贴肉", "贴身保留"]

ARTIFACT_PATTERNS = [
    re.compile(r"([\u4e00-\u9fff]{1,4}(?:绳|符|钱|铃|牌|佩|匣|盒|袋|册|刀|钩|线头|木牌|纸条))"),
]
VALID_ARTIFACT_LABEL_RE = re.compile(r"^(?:那|这|半截|一截|那截|这截|旧|粗|细|青|红|黑|残|破|湿|烂|半枚|一枚|半块|一块|那半截)?[\u4e00-\u9fff]{0,3}(?:绳|符|钱|铃|牌|佩|匣|盒|袋|册|刀|钩|木牌|纸条)$")
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

INVALID_ARTIFACT_LABEL_PREFIXES = ("不是", "觉到", "感觉", "几处", "某种", "分明", "突然", "正在", "像被", "像是", "是被", "倒像", "不是绳", "想起", "连着", "目前", "他们", "你要", "没有", "也许", "会让", "知道了", "买", "换", "解开", "松开", "攥紧")
INVALID_ARTIFACT_LABEL_PARTS = ("形状", "活物", "觉到", "几处", "分明", "倒像", "不是绳", "不是符", "不是牌", "触到", "看清", "拿起", "松开", "攥紧", "绑住", "勒出")
INVALID_HOLDER_PARTS = ("觉到", "几处", "分明", "倒像", "某种", "活物", "他", "她", "它")
INVALID_ARTIFACT_LABEL_PATTERNS = [
    re.compile(r"^(?:孟浮灯|他|她|他们|对方|目前|比如|或者|掌心|手指|勉强|从墙角|泡烂|想起|连着)"),
    re.compile(r"^[\u4e00-\u9fff]{0,4}(?:把|将|挪|摸|拿|想|看|攥|连|用|松开|绑住|拖着)"),
]
INVALID_MOTIF_LABEL_PREFIXES = (
    "一个",
    "两个",
    "一块",
    "一行",
    "不是",
    "可这",
    "轻则",
    "重则",
    "混着",
    "带着",
    "风带着",
    "只有",
    "只是",
    "像是",
    "像被",
    "他朝",
    "她朝",
    "盯着",
    "看着",
    "拖着",
    "拖到",
    "尸身",
    "把尸",
    "将尸",
    "有些",
    "那点",
    "半晌",
)
INVALID_MOTIF_LABEL_PARTS = (
    "两个字",
    "一个字",
    "扣钱",
    "领钱",
    "做活",
    "码头上",
    "往岸边",
    "到岸边",
    "盯着",
    "看着",
    "拖着",
    "尸身",
    "风带着",
    "混着",
    "不是码头",
    "不是绳",
    "不是牌",
)
INVALID_MOTIF_LABEL_PATTERNS = [
    re.compile(r"^(?:的|得|地)[\u4e00-\u9fff]{1,6}$"),
    re.compile(r"^[\u4e00-\u9fff]{1,2}则[\u4e00-\u9fff]{1,4}$"),
    re.compile(r"^[\u4e00-\u9fff]{1,6}(?:说过|做活|扣钱|领钱)$"),
    re.compile(r"^(?:风带着|混着|盯着|看着|拖着)[\u4e00-\u9fff]{1,6}$"),
]
VALID_ENVIRONMENT_MOTIF_RE = re.compile(r"^(?:窝棚|棚屋|岸边|桥洞|河道|码头|船舱|门口|窗边|屋里|渡口|旧码头|老码头|旧窝棚|破棚屋|旧棚屋)$")
VALID_SMELL_MOTIF_RE = re.compile(r"^(?:水腥气|血腥味|铁锈味|霉气|潮气|臭味|怪味|气味)$")


class MotifEntry(BaseModel):
    motif_id: str
    category: str
    label: str
    narrative_functions: list[str] = Field(default_factory=list)
    status: str = "active"
    recent_scene_ids: list[str] = Field(default_factory=list)
    recent_usage_count: int = 0
    recent_functions: list[str] = Field(default_factory=list)
    last_function: str = ""
    function_novelty_score: float = 1.0
    allow_next_scene: bool = True
    only_if_new_function: bool = False
    redundancy_risk: str = "low"
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
        raw_entries = data.get("active_motifs", []) if isinstance(data, dict) else []
        sanitized_entries: list[dict[str, Any]] = []
        for entry in raw_entries if isinstance(raw_entries, list) else []:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "").strip()
            category = str(entry.get("category") or "").strip()
            if not is_valid_motif_label(category, label):
                continue
            sanitized_entries.append(dict(entry))
        sanitized_data = dict(data or {})
        sanitized_data["active_motifs"] = sanitized_entries
        if hasattr(cls, "model_validate"):
            return cls.model_validate(sanitized_data)
        return cls.parse_obj(sanitized_data)


class RevelationTracker(BaseModel):
    chapter_id: str
    confirmed_facts: list[str] = Field(default_factory=list)
    suspected_facts: list[str] = Field(default_factory=list)
    unrevealed_facts: list[str] = Field(default_factory=list)
    forbidden_premature_reveals: list[str] = Field(default_factory=list)
    protagonist_known_facts: list[str] = Field(default_factory=list)
    reader_known_facts: list[str] = Field(default_factory=list)
    relationship_unknowns: list[str] = Field(default_factory=list)

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
    visibility: str = "unknown"
    significance_level: str = "medium"
    last_changed_scene: str = ""
    linked_facts: list[str] = Field(default_factory=list)

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
        raw_items = data.get("items", []) if isinstance(data, dict) else []
        sanitized_items: list[dict[str, Any]] = []
        for item in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            if not is_valid_artifact_label(label):
                continue
            sanitized = dict(item)
            sanitized["holder"] = sanitize_artifact_holder(str(item.get("holder") or "待确认"))
            sanitized_items.append(sanitized)
        sanitized_data = dict(data or {})
        sanitized_data["items"] = sanitized_items
        if hasattr(cls, "model_validate"):
            return cls.model_validate(sanitized_data)
        return cls.parse_obj(sanitized_data)


class ChapterProgress(BaseModel):
    chapter_id: str
    chapter_goal: str = ""
    protagonist_goal: str = ""
    protagonist_mode: str = "观察/求活"
    investigation_stage: str = "未启动"
    risk_level: str = "low"
    current_relationships: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    completed_scene_functions: list[str] = Field(default_factory=list)
    remaining_scene_functions: list[str] = Field(default_factory=list)
    consecutive_transition_scene_count: int = 0
    scene_summaries: list[dict[str, Any]] = Field(default_factory=list)
    chapter_structure_summary: dict[str, Any] = Field(default_factory=dict)

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


class SceneSummary(BaseModel):
    scene_id: str
    scene_function: str = ""
    new_information_items: list[str] = Field(default_factory=list)
    protagonist_decision: str = ""
    state_changes: list[str] = Field(default_factory=list)
    motifs_used: list[str] = Field(default_factory=list)
    motif_functions: dict[str, list[str]] = Field(default_factory=dict)
    artifacts_changed: list[dict[str, Any]] = Field(default_factory=list)
    open_questions_created: list[str] = Field(default_factory=list)
    open_questions_resolved: list[str] = Field(default_factory=list)
    reveal_changes: dict[str, list[str]] = Field(default_factory=dict)
    canon_risk_flags: list[str] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()


class ChapterStructureSummary(BaseModel):
    scene_function_table: list[dict[str, str]] = Field(default_factory=list)
    first_clue_scene_id: str = ""
    first_old_acquaintance_hint_scene_id: str = ""
    first_investigation_trigger_scene_id: str = ""
    first_artifact_change_scene_id: str = ""
    consecutive_transition_runs: list[dict[str, Any]] = Field(default_factory=list)

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


def normalize_fact_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = text.strip("-•·，。；：: ")
    return text


def split_sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[。！？!?；;])\s*", str(text or "")) if item.strip()]


def dedupe_facts(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = normalize_fact_text(value)
        if not text:
            continue
        key = re.sub(r"\s+", "", text)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


SUSPECTED_FACT_MARKERS = ["似乎", "像是", "仿佛", "也许", "可能", "隐约", "怀疑", "认得", "像曾见过", "未必"]
READER_KNOWN_MARKERS = ["看见", "看到", "摸到", "露出", "写着", "发现", "认出", "听见"]
VISIBILITY_OPEN_MARKERS = ["手里", "桌上", "门口", "窗边", "露出", "挂着", "看见", "亮出来"]
VISIBILITY_HIDDEN_MARKERS = ["袖里", "袖中", "怀里", "贴身", "腰间", "藏在", "塞回", "压在", "揣着"]
VISIBILITY_EXTERNALIZATION_MARKERS = ["递给", "亮给", "给人看", "摊给", "挂到门口", "挂到窗边", "让人看见", "摆到门口", "摆到窗边", "当众"]
RISK_LEVEL_MARKERS = {
    "high": ["差点", "险些", "暴露", "惹来", "盯上", "失手", "追上"],
    "medium": ["麻烦", "不敢", "更难", "迟疑", "阻力", "后果"],
}


def extract_fact_candidates_from_text(text: str) -> tuple[list[str], list[str]]:
    confirmed: list[str] = []
    suspected: list[str] = []
    for sentence in split_sentences(text):
        if any(marker in sentence for marker in DISCOVERY_MARKERS + READER_KNOWN_MARKERS):
            confirmed.append(sentence)
        if any(marker in sentence for marker in SUSPECTED_FACT_MARKERS):
            suspected.append(sentence)
    return dedupe_facts(confirmed), dedupe_facts(suspected)


def fact_list_difference(updated: list[str], original: list[str]) -> list[str]:
    original_keys = {re.sub(r"\s+", "", normalize_fact_text(item)) for item in original}
    return [item for item in dedupe_facts(updated) if re.sub(r"\s+", "", normalize_fact_text(item)) not in original_keys]


def extract_relationship_unknowns(chapter_state_text: str, story_state: dict[str, Any] | None) -> list[str]:
    sections = parse_markdown_sections(chapter_state_text)
    candidates = extract_bullets_from_section(sections.get("暂不展开的内容", []))
    protagonist = ((story_state or {}).get("characters") or {}).get("protagonist") or {}
    candidates.extend(normalize_string_list(protagonist.get("open_tensions", [])))
    return dedupe_facts([item for item in candidates if any(marker in item for marker in ["身份", "关系", "名字", "旧识", "来处", "是谁"])])[:12]


def build_relationship_status_snapshots(
    chapter_state_text: str,
    story_state: dict[str, Any] | None,
    confirmed_facts: list[str] | None = None,
    suspected_facts: list[str] | None = None,
    relationship_unknowns: list[str] | None = None,
) -> list[str]:
    snapshots: list[str] = []
    relationship_unknowns = relationship_unknowns or []
    suspected_facts = suspected_facts or []
    confirmed_facts = confirmed_facts or []

    for unknown in relationship_unknowns:
        names = extract_named_tokens(unknown)
        if not names:
            snapshots.append(f"陌生线索：{unknown}")
            continue
        for name in names:
            snapshots.append(f"{name}：陌生线索")

    for fact in suspected_facts:
        if any(marker in fact for marker in ["旧识", "认得", "像曾", "似曾", "记得"]):
            for name in extract_named_tokens(fact):
                snapshots.append(f"{name}：疑似旧识")

    for fact in confirmed_facts:
        if any(marker in fact for marker in ["确认", "认出", "原来", "就是", "旧识"]):
            for name in extract_named_tokens(fact):
                snapshots.append(f"{name}：已确认关系推进")

    for item in normalize_string_list([str(entry.get("delta") or "").strip() for entry in ((story_state or {}).get("relationship_deltas") or []) if isinstance(entry, dict)]):
        snapshots.append(item)
    return dedupe_facts(snapshots)[:8]


def extract_named_tokens(text: str) -> list[str]:
    cleaned = re.sub(r"(是谁|身份|来处|关系|真实身份|旧识)$", "", str(text or ""))
    matches = re.findall(r"[“\"『「]?([\u4e00-\u9fff]{2,4})[”\"』」]?", cleaned)
    skip = {"主角", "关系", "名字", "线索", "身份", "当前", "本场", "旧识"}
    return [item for item in dedupe_facts(matches) if item not in skip]


def infer_artifact_visibility(text: str, label: str) -> str:
    if any(marker in text for marker in VISIBILITY_HIDDEN_MARKERS):
        return "hidden"
    if any(marker in text for marker in VISIBILITY_OPEN_MARKERS):
        return "visible"
    if label and label in text:
        return "mentioned"
    return "unknown"


def infer_artifact_holder(text: str) -> str:
    if any(marker in text for marker in CARRIED_ARTIFACT_MARKERS):
        return "主角"
    match = re.search(r"([\u4e00-\u9fff]{2,4}).{0,4}(?:拿着|握着|带着|揣着|捏着)", text)
    if match:
        return sanitize_artifact_holder(match.group(1))
    return "待确认"


def infer_artifact_location(text: str, label: str, fallback: str = "待确认") -> str:
    if any(marker in text for marker in CARRIED_ARTIFACT_MARKERS):
        return "随身携带"
    for marker in LOCATION_CHANGE_MARKERS:
        match = re.search(rf"{re.escape(label)}.{{0,8}}{re.escape(marker)}([^，。；\n]+)", text)
        if match:
            return match.group(1).strip()
        reverse_match = re.search(rf"{re.escape(marker)}([^，。；\n]+).{{0,8}}{re.escape(label)}", text)
        if reverse_match:
            return reverse_match.group(1).strip()
    return fallback


def infer_artifact_significance(label: str, linked_facts: list[str], recent_usage_count: int = 0) -> str:
    if linked_facts or recent_usage_count >= 2:
        return "high"
    if label.endswith(("符", "牌", "佩", "匣", "盒")):
        return "medium"
    return "low"


def classify_investigation_stage(text: str, story_state: dict[str, Any] | None = None) -> str:
    combined = f"{text}\n{json.dumps(story_state or {}, ensure_ascii=False)}"
    if any(marker in combined for marker in ["查清", "追问", "调查", "跟踪", "探查", "问清"]):
        return "主动调查"
    if any(marker in combined for marker in ["记下", "留意", "盯着", "想起", "怀疑", "不敢忽略"]):
        return "被动留意"
    return "未启动"


def classify_protagonist_mode(text: str, story_state: dict[str, Any] | None = None) -> str:
    combined = f"{text}\n{json.dumps(story_state or {}, ensure_ascii=False)}"
    if any(marker in combined for marker in ["隐瞒", "藏起", "塞回", "压下"]):
        return "隐匿/压制"
    if any(marker in combined for marker in INVESTIGATION_MARKERS):
        return "调查/试探"
    if any(marker in combined for marker in ["决定", "转向", "回去", "取走"]):
        return "行动推进"
    return "观察/求活"


def classify_risk_level(text: str, story_state: dict[str, Any] | None = None) -> str:
    combined = f"{text}\n{json.dumps(story_state or {}, ensure_ascii=False)}"
    for level, markers in RISK_LEVEL_MARKERS.items():
        if any(marker in combined for marker in markers):
            return level
    return "low"


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


def previous_scene_id(scene_id: str) -> str | None:
    match = re.fullmatch(r"(ch\d+)_scene(\d+)", str(scene_id or "").strip())
    if not match:
        return None
    chapter_id = match.group(1)
    scene_number_text = match.group(2)
    scene_number = int(scene_number_text)
    if scene_number <= 1:
        return None
    return f"{chapter_id}_scene{scene_number - 1:0{len(scene_number_text)}d}"


def tracker_file_paths(chapter_id: str) -> dict[str, str]:
    return {
        "chapter_motif_tracker": f"{TRACKER_DIR}/{chapter_id}_chapter_motif_tracker.json",
        "revelation_tracker": f"{TRACKER_DIR}/{chapter_id}_revelation_tracker.json",
        "artifact_state": f"{TRACKER_DIR}/{chapter_id}_artifact_state.json",
        "chapter_progress": f"{TRACKER_DIR}/{chapter_id}_chapter_progress.json",
    }


def build_scene_summary_report_path(scene_id: str) -> str:
    return f"03_locked/reports/{scene_id}_scene_summary.json"


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


def clean_extracted_label(label: str) -> str:
    text = str(label or "").strip("“”‘’\"' ，。；：:、")
    text = re.sub(r"^(?:看见|看到|摸到|捡到|拾到|认出|确认|写着|露出|原来|竟是|把|将|那块|这块|那枚|这枚|一枚|一截|半截|那截|这截|是把|像是|仍把|松开|攥紧|摸出|看清|从墙角拿起|手指触到|勉强能看清|起那截)", "", text)
    text = re.sub(r"^(?:他的|她的|那条|这条|那只|这只)", "", text)
    return text.strip()


def normalize_motif_label(category: str, label: str) -> str:
    text = clean_extracted_label(label)
    if category == "environment_motif":
        match = re.search(r"(?:窝棚|棚屋|岸边|桥洞|河道|码头|船舱|门口|窗边|屋里|渡口)$", text)
        return match.group(0) if match else text
    if category == "smell_motif":
        match = re.search(r"([\u4e00-\u9fff]{0,2}(?:气味|味|臭|腥气|潮气|霉气))$", text)
        return match.group(1) if match else text
    if category == "memory_trigger_motif":
        if "说过" in text:
            return ""
        match = re.search(r"((?:想起|记起|梦见|闻见|看见)[\u4e00-\u9fff]{0,4})$", text)
        return match.group(1) if match else text
    return text


def is_valid_motif_label(category: str, label: str) -> bool:
    text = str(label or "").strip()
    if len(text) < 2 or len(text) > 8:
        return False
    if text in {"一个", "两个字", "一个字", "一块木牌", "一行小字"}:
        return False
    if any(text.startswith(prefix) for prefix in INVALID_MOTIF_LABEL_PREFIXES):
        return False
    if any(part in text for part in INVALID_MOTIF_LABEL_PARTS):
        return False
    if any(pattern.search(text) for pattern in INVALID_MOTIF_LABEL_PATTERNS):
        return False
    if category == "smell_motif" and not VALID_SMELL_MOTIF_RE.fullmatch(text):
        return False
    if category == "environment_motif" and not VALID_ENVIRONMENT_MOTIF_RE.fullmatch(text):
        return False
    if category == "memory_trigger_motif" and not text.startswith(("想起", "记起", "梦见", "闻见", "看见")):
        return False
    return True


def is_valid_artifact_label(label: str) -> bool:
    text = str(label or "").strip()
    if len(text) < 2 or len(text) > 6:
        return False
    if "和" in text:
        return False
    if any(text.startswith(prefix) for prefix in INVALID_ARTIFACT_LABEL_PREFIXES):
        return False
    if any(part in text for part in INVALID_ARTIFACT_LABEL_PARTS):
        return False
    if any(pattern.search(text) for pattern in INVALID_ARTIFACT_LABEL_PATTERNS):
        return False
    return bool(VALID_ARTIFACT_LABEL_RE.fullmatch(text))


def sanitize_artifact_holder(holder: str) -> str:
    text = str(holder or "").strip()
    if not text:
        return "待确认"
    if text in {"主角", "孟浮灯", "待确认"}:
        return text
    if any(part in text for part in INVALID_HOLDER_PARTS):
        return "待确认"
    if "和" in text:
        return "待确认"
    if re.search(r"(绳|符|牌|钱|铃|佩|匣|盒|袋|册|刀|钩)$", text):
        return "待确认"
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}", text):
        return "待确认"
    return text


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
                label = normalize_motif_label(category, label)
                if len(label) < 2:
                    continue
                if not is_valid_motif_label(category, label):
                    continue
                if category == "artifact_motif" and not is_valid_artifact_label(label):
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
                scene_function = classify_scene_function(scene_text)
                entry = MotifEntry(
                    motif_id=motif_id,
                    category=category,
                    label=label,
                    narrative_functions=[scene_function],
                    status="active",
                    recent_scene_ids=[scene_id],
                    recent_usage_count=1,
                    recent_functions=[scene_function],
                    last_function=scene_function,
                    function_novelty_score=1.0,
                    allow_next_scene=True,
                    only_if_new_function=False,
                    redundancy_risk="low",
                    notes="bootstrap_from_recent_locked_scenes",
                )
                motif_map[motif_id] = entry
            else:
                scene_function = classify_scene_function(scene_text)
                if scene_id not in entry.recent_scene_ids:
                    entry.recent_scene_ids.append(scene_id)
                    entry.recent_usage_count += 1
                update_motif_function_tracking(entry, scene_function)
    for entry in motif_map.values():
        if not entry.recent_functions and entry.last_function:
            entry.recent_functions = [entry.last_function]
        if not entry.last_function and entry.recent_functions:
            entry.last_function = entry.recent_functions[-1]
    return ChapterMotifTracker(chapter_id=chapter_id, active_motifs=list(motif_map.values()))


def bootstrap_revelation_tracker(chapter_id: str, chapter_state_text: str, story_state: dict[str, Any] | None) -> RevelationTracker:
    story_state = story_state or {}
    sections = parse_markdown_sections(chapter_state_text)
    protagonist = ((story_state.get("characters") or {}).get("protagonist") or {})
    confirmed_facts = normalize_string_list(protagonist.get("known_facts", []))
    suspected_facts = normalize_string_list(protagonist.get("open_tensions", []))
    unrevealed_facts = normalize_string_list(extract_bullets_from_section(sections.get("已锁定线索", [])))
    forbidden_premature_reveals = normalize_string_list(extract_bullets_from_section(sections.get("暂不展开的内容", [])))
    protagonist_known_facts = list(confirmed_facts)
    reader_known_facts = dedupe_facts(confirmed_facts + unrevealed_facts)
    relationship_unknowns = extract_relationship_unknowns(chapter_state_text, story_state)
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
        protagonist_known_facts=protagonist_known_facts[:12],
        reader_known_facts=reader_known_facts[:16],
        relationship_unknowns=relationship_unknowns[:12],
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
                visibility="unknown",
                significance_level="medium",
                last_changed_scene=str(item.get("last_seen_in") or "").strip(),
                linked_facts=dedupe_facts(normalize_string_list(item.get("linked_facts", [])))[:6],
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
    protagonist_known_facts = normalize_string_list((((story_state or {}).get("characters") or {}).get("protagonist") or {}).get("known_facts", []))
    protagonist_open_tensions = normalize_string_list((((story_state or {}).get("characters") or {}).get("protagonist") or {}).get("open_tensions", []))
    unrevealed_facts = normalize_string_list(extract_bullets_from_section(sections.get("已锁定线索", [])))
    protagonist_mode = classify_protagonist_mode(chapter_state_text, story_state)
    investigation_stage = classify_investigation_stage(chapter_state_text, story_state)
    risk_level = classify_risk_level(chapter_state_text, story_state)
    relationship_unknowns = extract_relationship_unknowns(chapter_state_text, story_state)
    current_relationships = build_relationship_status_snapshots(
        chapter_state_text,
        story_state,
        confirmed_facts=protagonist_known_facts,
        suspected_facts=protagonist_open_tensions,
        relationship_unknowns=relationship_unknowns,
    )
    unresolved_questions = dedupe_facts(
        protagonist_open_tensions
        + extract_bullets_from_section(sections.get("暂不展开的内容", []))
        + unrevealed_facts
    )[:8]
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
        protagonist_goal="；".join(protagonist_goal[:2]) if protagonist_goal else "推动当前章内未解决问题。",
        protagonist_mode=protagonist_mode,
        investigation_stage=investigation_stage,
        risk_level=risk_level,
        current_relationships=current_relationships[:6],
        unresolved_questions=unresolved_questions,
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

    revelation_payload = revelation_tracker.to_dict()
    revelation_payload.setdefault("revealed_facts", revelation_payload.get("confirmed_facts", []))
    revelation_payload.setdefault("pending_facts", revelation_payload.get("suspected_facts", []))
    revelation_payload.setdefault("forbidden_early_reveals", revelation_payload.get("forbidden_premature_reveals", []))

    chapter_progress_payload = chapter_progress.to_dict()
    chapter_progress_payload.setdefault("state_tracker_summary", {
        "investigation_stage": chapter_progress_payload.get("investigation_stage", "未启动"),
        "risk_level": chapter_progress_payload.get("risk_level", "low"),
        "protagonist_mode": chapter_progress_payload.get("protagonist_mode", "观察/求活"),
    })

    return {
        "chapter_motif_tracker": chapter_motif_tracker.to_dict(),
        "revelation_tracker": revelation_payload,
        "artifact_state": artifact_state.to_dict(),
        "chapter_progress": chapter_progress_payload,
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
    for unknown in revelation_tracker.get("relationship_unknowns", []) if isinstance(revelation_tracker, dict) else []:
        unknown_text = str(unknown).strip()
        if not unknown_text:
            continue
        tokens = extract_named_tokens(unknown_text) or extract_fact_tokens(unknown_text)
        if tokens and any(token in draft_text for token in tokens) and any(marker in draft_text for marker in GENERIC_FAMILIARITY_MARKERS):
            violations.append(f"关系未知项“{unknown_text}”仍未确认，但正文已经写成熟识关系。")
    return violations[:3]


def detect_artifact_state_conflicts(draft_text: str, artifact_state: dict[str, Any]) -> list[str]:
    def is_unresolved(value: str) -> bool:
        normalized = value.strip()
        return not normalized or normalized == "待确认" or "待确认" in normalized

    def label_present(label: str) -> bool:
        if not label:
            return False
        if len(label) <= 1:
            return False
        if label in draft_text:
            return True
        if "和" in label:
            parts = [part.strip() for part in label.split("和") if part.strip()]
            if len(parts) >= 2 and all(part in draft_text for part in parts):
                return True
        return False

    def holder_matches(holder: str) -> bool:
        if holder in PROTAGONIST_HOLDER_ALIASES:
            return any(alias in draft_text for alias in PROTAGONIST_HOLDER_ALIASES)
        return holder in draft_text

    def location_matches(location: str) -> bool:
        if location in draft_text:
            return True
        if location in {"随身携带", "贴身保留"}:
            return any(marker in draft_text for marker in CARRIED_ARTIFACT_MARKERS + BODY_CARRY_LOCATION_MARKERS)
        return False

    def hidden_visibility_violated(label: str) -> bool:
        relevant_sentences = [sentence for sentence in split_sentences(draft_text) if label in sentence]
        if not relevant_sentences:
            return False
        for sentence in relevant_sentences:
            if any(marker in sentence for marker in VISIBILITY_EXTERNALIZATION_MARKERS):
                return True
        return False

    conflicts: list[str] = []
    for item in artifact_state.get("items", []) if isinstance(artifact_state, dict) else []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        holder = str(item.get("holder") or "").strip()
        location = str(item.get("location") or "").strip()
        visibility = str(item.get("visibility") or "").strip()
        if not is_valid_artifact_label(label):
            continue
        if not label_present(label):
            continue
        if holder and holder in PROTAGONIST_HOLDER_ALIASES and not holder_matches(holder) and any(marker in draft_text for marker in CARRIED_ARTIFACT_MARKERS):
            conflicts.append(f"物件“{label}”当前持有者应为“{holder}”，但正文写法与现有 artifact_state 不一致。")
        if location and not is_unresolved(location) and not location_matches(location) and any(marker in draft_text for marker in LOCATION_CHANGE_MARKERS + CARRIED_ARTIFACT_MARKERS + BODY_CARRY_LOCATION_MARKERS):
            conflicts.append(f"物件“{label}”当前所在位置应为“{location}”，但正文写法与现有 artifact_state 不一致。")
        if visibility == "hidden" and hidden_visibility_violated(label):
            conflicts.append(f"物件“{label}”当前应保持隐藏，但正文把它写成对外可见。")
    return conflicts[:3]


def merge_scene_ids(existing: list[str], scene_id: str) -> list[str]:
    merged = [item for item in existing if item != scene_id]
    merged.append(scene_id)
    return merged[-3:]


def merge_recent_functions(existing: list[str], scene_function: str) -> list[str]:
    normalized = [str(item).strip() for item in existing if str(item).strip()]
    if not scene_function:
        return normalized[-3:]
    normalized.append(scene_function)
    return normalized[-3:]


def count_trailing_same_function(values: list[str], scene_function: str) -> int:
    if not scene_function:
        return 0
    count = 0
    for item in reversed(values):
        if item != scene_function:
            break
        count += 1
    return count


def calculate_function_novelty_score(previous_functions: list[str], scene_function: str) -> float:
    history = [str(item).strip() for item in previous_functions if str(item).strip()]
    if not scene_function:
        return 0.0
    if not history:
        return 1.0
    if scene_function not in history:
        return 1.0
    if history[-1] == scene_function:
        return 0.0
    return 0.4


def assess_motif_redundancy_risk(
    recent_usage_count: int,
    recent_functions: list[str],
    function_novelty_score: float,
    forced_only_if_new: bool = False,
) -> str:
    last_function = recent_functions[-1] if recent_functions else ""
    same_function_streak = count_trailing_same_function(recent_functions, last_function)
    if forced_only_if_new or same_function_streak >= 2 or (recent_usage_count >= 3 and function_novelty_score <= 0.0):
        return "high"
    if same_function_streak >= 1 and function_novelty_score < 1.0:
        return "medium"
    if recent_usage_count >= 3:
        return "medium"
    return "low"


def update_motif_function_tracking(entry: MotifEntry, scene_function: str, forced_only_if_new: bool = False) -> None:
    previous_functions = [str(item).strip() for item in entry.recent_functions if str(item).strip()]
    if not previous_functions and entry.last_function:
        previous_functions = [entry.last_function]

    novelty_score = calculate_function_novelty_score(previous_functions, scene_function)
    entry.recent_functions = merge_recent_functions(previous_functions, scene_function)
    if scene_function:
        entry.last_function = scene_function
        if scene_function not in entry.narrative_functions:
            entry.narrative_functions.append(scene_function)

    entry.function_novelty_score = novelty_score
    entry.redundancy_risk = assess_motif_redundancy_risk(
        recent_usage_count=entry.recent_usage_count,
        recent_functions=entry.recent_functions,
        function_novelty_score=entry.function_novelty_score,
        forced_only_if_new=forced_only_if_new,
    )
    entry.only_if_new_function = forced_only_if_new or entry.redundancy_risk in {"medium", "high"}
    entry.allow_next_scene = entry.redundancy_risk != "high"


def build_state_changes(previous_progress: ChapterProgress, updated_progress: ChapterProgress) -> list[str]:
    changes: list[str] = []
    for field_name, label in [
        ("protagonist_mode", "protagonist_mode"),
        ("investigation_stage", "investigation_stage"),
        ("risk_level", "risk_level"),
    ]:
        before = str(getattr(previous_progress, field_name, "") or "").strip()
        after = str(getattr(updated_progress, field_name, "") or "").strip()
        if after and after != before:
            changes.append(f"{label}: {before or '未记录'} -> {after}")
    return changes


def build_artifact_changes(previous_state: ArtifactState, updated_state: ArtifactState, scene_id: str) -> list[dict[str, Any]]:
    previous_by_label = {item.label: item for item in previous_state.items if item.label}
    changes: list[dict[str, Any]] = []
    for item in updated_state.items:
        if item.last_changed_scene != scene_id:
            continue
        previous = previous_by_label.get(item.label)
        change_types: list[str] = []
        if previous is None:
            change_types.append("introduced")
        else:
            if item.holder != previous.holder:
                change_types.append("holder")
            if item.location != previous.location:
                change_types.append("location")
            if item.visibility != previous.visibility:
                change_types.append("visibility")
            if item.significance_level != previous.significance_level:
                change_types.append("significance_level")
        if previous is None or change_types:
            changes.append(
                {
                    "label": item.label,
                    "holder": item.holder,
                    "location": item.location,
                    "visibility": item.visibility,
                    "significance_level": item.significance_level,
                    "change_types": change_types or ["introduced"],
                }
            )
    return changes


def is_old_acquaintance_hint(summary: dict[str, Any]) -> bool:
    haystack_parts = [
        str(summary.get("protagonist_decision") or ""),
        " ".join(normalize_string_list(summary.get("new_information_items", []))),
        " ".join(normalize_string_list(summary.get("open_questions_created", []))),
        " ".join(normalize_string_list(summary.get("state_changes", []))),
    ]
    reveal_changes = summary.get("reveal_changes", {}) if isinstance(summary.get("reveal_changes"), dict) else {}
    haystack_parts.extend(" ".join(normalize_string_list(values)) for values in reveal_changes.values() if isinstance(values, list))
    haystack = " ".join(part for part in haystack_parts if part)
    return any(marker in haystack for marker in ["旧识", "相识", "熟悉", "认得", "似曾", "以前", "从前"])


def build_chapter_structure_summary(scene_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    scene_function_table = [
        {
            "scene_id": str(item.get("scene_id") or "").strip(),
            "scene_function": str(item.get("scene_function") or "").strip(),
        }
        for item in scene_summaries
        if str(item.get("scene_id") or "").strip()
    ]
    first_clue_scene_id = ""
    first_old_acquaintance_hint_scene_id = ""
    first_investigation_trigger_scene_id = ""
    first_artifact_change_scene_id = ""
    consecutive_transition_runs: list[dict[str, Any]] = []
    current_transition_run: list[str] = []

    for summary in scene_summaries:
        scene_id = str(summary.get("scene_id") or "").strip()
        scene_function = str(summary.get("scene_function") or "").strip()
        new_information_items = normalize_string_list(summary.get("new_information_items", []))
        state_changes = normalize_string_list(summary.get("state_changes", []))
        artifacts_changed = summary.get("artifacts_changed", []) if isinstance(summary.get("artifacts_changed"), list) else []

        if not first_clue_scene_id and (new_information_items or scene_function == "发现线索"):
            first_clue_scene_id = scene_id
        if not first_old_acquaintance_hint_scene_id and is_old_acquaintance_hint(summary):
            first_old_acquaintance_hint_scene_id = scene_id
        if not first_investigation_trigger_scene_id:
            investigation_shift = any(change.startswith("investigation_stage:") and not change.endswith("-> 未启动") for change in state_changes)
            if scene_function == "触发调查" or investigation_shift:
                first_investigation_trigger_scene_id = scene_id
        if not first_artifact_change_scene_id and artifacts_changed:
            first_artifact_change_scene_id = scene_id

        if scene_function == "过渡/氛围":
            current_transition_run.append(scene_id)
        else:
            if len(current_transition_run) >= 2:
                consecutive_transition_runs.append(
                    {
                        "start_scene_id": current_transition_run[0],
                        "end_scene_id": current_transition_run[-1],
                        "length": len(current_transition_run),
                        "scene_ids": list(current_transition_run),
                    }
                )
            current_transition_run = []

    if len(current_transition_run) >= 2:
        consecutive_transition_runs.append(
            {
                "start_scene_id": current_transition_run[0],
                "end_scene_id": current_transition_run[-1],
                "length": len(current_transition_run),
                "scene_ids": list(current_transition_run),
            }
        )

    return ChapterStructureSummary(
        scene_function_table=scene_function_table[-12:],
        first_clue_scene_id=first_clue_scene_id,
        first_old_acquaintance_hint_scene_id=first_old_acquaintance_hint_scene_id,
        first_investigation_trigger_scene_id=first_investigation_trigger_scene_id,
        first_artifact_change_scene_id=first_artifact_change_scene_id,
        consecutive_transition_runs=consecutive_transition_runs[-4:],
    ).to_dict()


def build_scene_summary(
    scene_id: str,
    scene_function: str,
    reviewer_result: dict[str, Any],
    previous_revelation_tracker: RevelationTracker,
    updated_revelation_tracker: RevelationTracker,
    previous_artifact_state: ArtifactState,
    updated_artifact_state: ArtifactState,
    previous_progress: ChapterProgress,
    updated_progress: ChapterProgress,
    motif_entries: list[MotifEntry],
) -> dict[str, Any]:
    new_information_items = normalize_string_list((reviewer_result.get("information_gain") or {}).get("new_information_items", []))
    protagonist_decision = str((reviewer_result.get("character_decision") or {}).get("decision_detail") or "").strip()
    artifacts_changed = build_artifact_changes(previous_artifact_state, updated_artifact_state, scene_id)
    reveal_changes = {
        "confirmed_added": fact_list_difference(updated_revelation_tracker.confirmed_facts, previous_revelation_tracker.confirmed_facts),
        "suspected_added": fact_list_difference(updated_revelation_tracker.suspected_facts, previous_revelation_tracker.suspected_facts),
        "protagonist_known_added": fact_list_difference(updated_revelation_tracker.protagonist_known_facts, previous_revelation_tracker.protagonist_known_facts),
        "reader_known_added": fact_list_difference(updated_revelation_tracker.reader_known_facts, previous_revelation_tracker.reader_known_facts),
        "unrevealed_resolved": fact_list_difference(previous_revelation_tracker.unrevealed_facts, updated_revelation_tracker.unrevealed_facts),
        "relationship_unknowns_resolved": fact_list_difference(previous_revelation_tracker.relationship_unknowns, updated_revelation_tracker.relationship_unknowns),
    }
    open_questions_created = fact_list_difference(updated_progress.unresolved_questions, previous_progress.unresolved_questions)
    open_questions_resolved = fact_list_difference(previous_progress.unresolved_questions, updated_progress.unresolved_questions)

    motif_functions: dict[str, list[str]] = {}
    motifs_used: list[str] = []
    for entry in motif_entries:
        if entry.label not in motifs_used:
            motifs_used.append(entry.label)
        motif_functions[entry.label] = normalize_string_list(entry.narrative_functions)

    return SceneSummary(
        scene_id=scene_id,
        scene_function=scene_function,
        new_information_items=new_information_items,
        protagonist_decision=protagonist_decision,
        state_changes=build_state_changes(previous_progress, updated_progress),
        motifs_used=motifs_used,
        motif_functions=motif_functions,
        artifacts_changed=artifacts_changed,
        open_questions_created=open_questions_created,
        open_questions_resolved=open_questions_resolved,
        reveal_changes={key: value for key, value in reveal_changes.items() if value},
        canon_risk_flags=normalize_string_list((reviewer_result.get("canon_consistency") or {}).get("consistency_issues", [])),
    ).to_dict()


def derive_actual_tracker_updates(root: Path, task_text: str, locked_file: str, reviewer_result: dict[str, Any], tracker_bundle: dict[str, Any]) -> dict[str, Any]:
    chapter_id = chapter_id_from_task_or_locked(task_text, locked_file)
    scene_id = scene_id_from_locked_file(locked_file)
    locked_text = (root / locked_file).read_text(encoding="utf-8") if (root / locked_file).exists() else ""

    chapter_motif_tracker = ChapterMotifTracker.from_dict(tracker_bundle.get("chapter_motif_tracker", {"chapter_id": chapter_id}))
    revelation_tracker = RevelationTracker.from_dict(tracker_bundle.get("revelation_tracker", {"chapter_id": chapter_id}))
    artifact_state = ArtifactState.from_dict(tracker_bundle.get("artifact_state", {"chapter_id": chapter_id}))
    chapter_progress = ChapterProgress.from_dict(tracker_bundle.get("chapter_progress", {"chapter_id": chapter_id}))
    previous_revelation_tracker = RevelationTracker.from_dict(revelation_tracker.to_dict())
    previous_artifact_state = ArtifactState.from_dict(artifact_state.to_dict())
    previous_progress = ChapterProgress.from_dict(chapter_progress.to_dict())

    motif_map = {entry.motif_id: entry for entry in chapter_motif_tracker.active_motifs}
    reviewer_scene_function = str(extract_markdown_field(task_text, "scene_function") or classify_scene_function(locked_text)).strip() or classify_scene_function(locked_text)
    motif_redundancy = reviewer_result.get("motif_redundancy") or {}
    repeated_motifs = normalize_string_list(motif_redundancy.get("repeated_motifs", []))
    stale_function_motifs = normalize_string_list(motif_redundancy.get("stale_function_motifs", []))
    consecutive_same_function_motifs = normalize_string_list(motif_redundancy.get("consecutive_same_function_motifs", []))
    for category, label in extract_candidate_motifs_from_text(locked_text):
        motif_id = f"{category}_{slugify_label(label)}"
        entry = motif_map.get(motif_id)
        if entry is None:
            entry = MotifEntry(
                motif_id=motif_id,
                category=category,
                label=label,
                narrative_functions=[reviewer_scene_function],
                recent_scene_ids=[scene_id],
                recent_usage_count=1,
                recent_functions=[reviewer_scene_function],
                last_function=reviewer_scene_function,
                function_novelty_score=1.0,
                allow_next_scene=True,
                only_if_new_function=False,
                redundancy_risk="low",
            )
            motif_map[motif_id] = entry
        else:
            entry.recent_scene_ids = merge_scene_ids(entry.recent_scene_ids, scene_id)
            entry.recent_usage_count = min(max(entry.recent_usage_count + 1, len(entry.recent_scene_ids)), 99)
            force_only_if_new = (
                label in stale_function_motifs
                or label in consecutive_same_function_motifs
                or (label in repeated_motifs and not motif_redundancy.get("repetition_has_new_function", True))
            )
            update_motif_function_tracking(entry, reviewer_scene_function, forced_only_if_new=force_only_if_new)
            entry.notes = "locked_scene_repeated_without_new_function" if force_only_if_new else entry.notes
    chapter_motif_tracker.active_motifs = list(motif_map.values())

    reviewer_new_facts = normalize_string_list((reviewer_result.get("information_gain") or {}).get("new_information_items", []))
    text_confirmed, text_suspected = extract_fact_candidates_from_text(locked_text)
    new_facts = dedupe_facts(reviewer_new_facts + text_confirmed)
    revelation_tracker.confirmed_facts = dedupe_facts(revelation_tracker.confirmed_facts + new_facts)[:16]
    revelation_tracker.protagonist_known_facts = dedupe_facts(revelation_tracker.protagonist_known_facts + reviewer_new_facts)[:16]
    revelation_tracker.reader_known_facts = dedupe_facts(revelation_tracker.reader_known_facts + new_facts + text_suspected)[:20]
    revelation_tracker.suspected_facts = dedupe_facts(revelation_tracker.suspected_facts + text_suspected)[:16]
    revelation_tracker.unrevealed_facts = [item for item in revelation_tracker.unrevealed_facts if item not in new_facts][:16]
    revelation_tracker.relationship_unknowns = [
        item for item in revelation_tracker.relationship_unknowns if not any(token in " ".join(new_facts) for token in extract_fact_tokens(item))
    ][:12]

    artifact_map = {item.item_id: item for item in artifact_state.items}
    artifact_by_label = {item.label: item for item in artifact_state.items if item.label}
    for category, label in extract_candidate_motifs_from_text(locked_text):
        if category != "artifact_motif":
            continue
        item_id = f"artifact_{slugify_label(label)}"
        item = artifact_map.get(item_id) or artifact_by_label.get(label)
        if item is None:
            item = ArtifactStateItem(item_id=item_id, label=label, last_changed_scene=scene_id)
            artifact_map[item_id] = item
            artifact_by_label[label] = item
        elif item.item_id != item_id:
            artifact_map.pop(item.item_id, None)
            item.item_id = item_id
            artifact_map[item_id] = item
        item.last_changed_scene = scene_id
        item.holder = infer_artifact_holder(locked_text) if label in locked_text else item.holder
        item.location = infer_artifact_location(locked_text, label, fallback=item.location)
        item.visibility = infer_artifact_visibility(locked_text, label)
        linked_facts = [fact for fact in revelation_tracker.confirmed_facts + revelation_tracker.suspected_facts if label in fact]
        item.linked_facts = dedupe_facts(item.linked_facts + linked_facts)[:6]
        related_motif = motif_map.get(f"artifact_motif_{slugify_label(label)}")
        item.significance_level = infer_artifact_significance(label, item.linked_facts, related_motif.recent_usage_count if related_motif else 0)
    artifact_state.items = list(artifact_map.values())

    completed = [item for item in chapter_progress.completed_scene_functions if not item.startswith(f"{scene_id}: ")]
    completed.append(f"{scene_id}: {reviewer_scene_function}")
    chapter_progress.completed_scene_functions = completed[-8:]
    remaining = [item for item in chapter_progress.remaining_scene_functions if item != reviewer_scene_function]
    chapter_progress.remaining_scene_functions = remaining
    chapter_progress.consecutive_transition_scene_count = chapter_progress.consecutive_transition_scene_count + 1 if reviewer_scene_function == "过渡/氛围" else 0
    chapter_progress.protagonist_goal = "；".join(normalize_string_list((revelation_tracker.protagonist_known_facts or [])[:2])) or chapter_progress.protagonist_goal or "推动当前章内未解决问题。"
    chapter_progress.protagonist_mode = classify_protagonist_mode(locked_text, {"reviewer_result": reviewer_result})
    chapter_progress.investigation_stage = classify_investigation_stage(locked_text, {"reviewer_result": reviewer_result, "suspected_facts": revelation_tracker.suspected_facts})
    chapter_progress.risk_level = classify_risk_level(locked_text, {"reviewer_result": reviewer_result})
    chapter_progress.current_relationships = build_relationship_status_snapshots(
        locked_text,
        {"relationship_deltas": [{"delta": item} for item in chapter_progress.current_relationships]},
        confirmed_facts=revelation_tracker.confirmed_facts,
        suspected_facts=revelation_tracker.suspected_facts,
        relationship_unknowns=revelation_tracker.relationship_unknowns,
    )[:8]
    chapter_progress.unresolved_questions = dedupe_facts(
        chapter_progress.unresolved_questions + revelation_tracker.suspected_facts + revelation_tracker.relationship_unknowns + revelation_tracker.unrevealed_facts
    )[:10]
    motif_entries = [entry for entry in chapter_motif_tracker.active_motifs if entry.label in locked_text]
    scene_summary = build_scene_summary(
        scene_id=scene_id,
        scene_function=reviewer_scene_function,
        reviewer_result=reviewer_result,
        previous_revelation_tracker=previous_revelation_tracker,
        updated_revelation_tracker=revelation_tracker,
        previous_artifact_state=previous_artifact_state,
        updated_artifact_state=artifact_state,
        previous_progress=previous_progress,
        updated_progress=chapter_progress,
        motif_entries=motif_entries,
    )
    scene_summaries = [
        item
        for item in chapter_progress.scene_summaries
        if isinstance(item, dict) and str(item.get("scene_id") or "").strip() != scene_id
    ]
    scene_summaries.append(scene_summary)
    chapter_progress.scene_summaries = scene_summaries[-12:]
    chapter_progress.chapter_structure_summary = build_chapter_structure_summary(chapter_progress.scene_summaries)

    return {
        "chapter_motif_tracker": chapter_motif_tracker.to_dict(),
        "revelation_tracker": RevelationTracker.from_dict(revelation_tracker.to_dict()).to_dict(),
        "artifact_state": artifact_state.to_dict(),
        "chapter_progress": chapter_progress.to_dict(),
        "scene_summary_report": {
            "chapter_id": chapter_id,
            "scene_id": scene_id,
            "locked_file": locked_file,
            "scene_summary": scene_summary,
            "chapter_structure_summary": chapter_progress.chapter_structure_summary,
        },
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
    scene_id = scene_id_from_locked_file(locked_file)
    chapter_state_path = extract_markdown_field(task_text, "chapter_state")
    chapter_state_text = (root / chapter_state_path).read_text(encoding="utf-8") if chapter_state_path and (root / chapter_state_path).exists() else ""
    story_state_path = root / "03_locked/state/story_state.json"
    story_state = safe_load_json(story_state_path)
    tracker_bundle = load_tracker_bundle(
        root,
        chapter_id,
        chapter_state_text=chapter_state_text,
        story_state=story_state,
        upto_scene_id=previous_scene_id(scene_id),
    )
    updated_bundle = derive_actual_tracker_updates(root, task_text, locked_file, reviewer_result, tracker_bundle)
    outputs = save_tracker_bundle(root, updated_bundle, chapter_id)
    scene_summary_report = updated_bundle.get("scene_summary_report")
    if isinstance(scene_summary_report, dict):
        report_path = build_scene_summary_report_path(scene_id)
        save_json(root / report_path, scene_summary_report)
        outputs["scene_summary_report_file"] = report_path
    return outputs
