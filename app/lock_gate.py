import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from chapter_trackers import (
    classify_scene_function,
    detect_artifact_state_conflicts,
    detect_forbidden_reveal_violations,
    load_tracker_bundle,
)
from deepseek_supervisor import SCENE_FUNCTION_TO_TYPE, build_scene_type_control, load_scene_type_policy

from review_models import (
    RepairMode,
    ReviewIssue,
    ReviewIssueType,
    ReviewSeverity,
    ReviewStatus,
    StructuredReviewResult,
    build_repair_plan,
    build_structured_review_result,
)


ROOT = Path(__file__).resolve().parent.parent
GENERIC_REDUNDANCY_REASONS = {"有新功能。", "无重复。", "母题复读。", "结构上可锁定。", "可锁定。"}
INVESTIGATION_MARKERS = ["追问", "打听", "调查", "跟踪", "查清", "问清", "探查"]
ARTIFACT_CHANGE_MARKERS = ["塞回", "藏在", "摸出来", "揣着", "露出", "挂着", "放在", "留在", "压在"]
RELATIONSHIP_CHANGE_MARKERS = ["旧识", "相识", "认得", "名字", "两个人", "关系", "她曾", "她总"]
RISK_CHANGE_MARKERS = ["差点", "险些", "暴露", "惹来", "更难", "盯上", "麻烦"]
GOAL_CHANGE_MARKERS = [
    "决定",
    "改成",
    "暂缓",
    "转向",
    "放弃",
    "回去",
    "记下",
    "隐瞒",
    "先避开",
    "不再照旧",
    "换一种",
    "改明白了",
    "先处理",
    "先绕开",
    "处理顺序",
    "换了方向",
    "改了手上的做法",
    "收尾路数",
]
REALISM_TONE_MARKERS = ["底层现实主义修仙", "底层求活", "不要跳成大场面", "不要引入新的组织或职位称呼", "不要一上来就把更高层真相全部掀开"]
SPECTACLE_DRIFT_MARKERS = [
    "渗血",
    "青烟",
    "黑血",
    "冷光",
    "发烫",
    "忽明忽暗",
    "蛛网状纹路",
    "浮出半张人脸",
    "烙进",
    "抽搐着扭向",
    "泪痣正在渗出暗红",
    "化作一缕青烟",
    "突然变得滚烫",
    "活物",
    "司命府",
    "契约",
    "苏醒",
]
INSTITUTION_DRIFT_MARKERS = ["司命使", "清道坊", "失踪人口核查", "禁录符", "漕运三十六行"]


class LockGateCheck(BaseModel):
    name: str = Field(min_length=1)
    passed: bool
    details: str = Field(min_length=1)


class LockGateOverride(BaseModel):
    present: bool
    reason: str = ""


class LockGateReport(BaseModel):
    task_id: str = Field(min_length=1)
    passed: bool
    checks: list[LockGateCheck] = Field(default_factory=list)
    policy_override: LockGateOverride = Field(default_factory=lambda: LockGateOverride(present=False, reason=""))

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")


def extract_markdown_field(task_text: str, field_name: str) -> str | None:
    pattern = rf"(?ms)^#\s*{re.escape(field_name)}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, task_text)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


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


def normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def safe_load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def infer_chapter_id(task_text: str) -> str:
    for field in ("based_on", "output_target", "chapter_state", "task_id"):
        value = extract_markdown_field(task_text, field) or ""
        match = re.search(r"(ch\d+)_scene\d+", value)
        if match:
            return match.group(1)
    return ""


def infer_previous_scene_id(task_text: str) -> str | None:
    based_on = extract_markdown_field(task_text, "based_on") or ""
    match = re.search(r"(ch\d+_scene\d+)", based_on)
    if match:
        return match.group(1)
    return None


def read_task_path(task_text: str, field_name: str) -> tuple[str, str]:
    rel_path = (extract_markdown_field(task_text, field_name) or "").strip()
    if not rel_path:
        return "", ""
    path = ROOT / rel_path
    if not path.exists():
        return rel_path, ""
    try:
        return rel_path, path.read_text(encoding="utf-8")
    except OSError:
        return rel_path, ""


def tokenize_text(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]{1,6}|[A-Za-z0-9_]+", str(text or ""))


def is_generic_requirement(text: str) -> bool:
    text = str(text or "")
    generic_markers = [
        "至少",
        "必须",
        "新的",
        "新信息",
        "状态变量",
        "变化",
        "动作",
        "决策",
        "风险",
        "关系",
        "物件",
        "认知",
        "目标",
        "卷入",
        "黑幕",
        "线索",
        "尸体",
        "名字",
        "求活",
        "底层",
        "压力来源",
        "行动边界",
        "现实问题",
    ]
    return any(marker in text for marker in generic_markers)


def requirement_matches_evidence(requirement: str, evidences: list[str], draft_text: str = "") -> bool:
    requirement_text = str(requirement or "").strip()
    if not requirement_text:
        return True
    haystacks = [str(item).strip() for item in evidences if str(item).strip()]
    if draft_text:
        haystacks.append(str(draft_text).strip())

    def semantic_match(haystack: str) -> bool:
        if not haystack:
            return False
        if "阿绣" in requirement_text and "阿绣" in haystack:
            if any(marker in requirement_text for marker in ["确认", "看错", "误读"]) and any(marker in haystack for marker in ["确认", "浮出来", "看清", "不是", "眼花", "看错", "犯晕"]):
                return True
        if any(marker in requirement_text for marker in ["记住", "先不说", "不说", "不声张", "压在心里"]):
            remembered = any(marker in haystack for marker in ["记住", "记下", "先记着", "先记住"])
            withheld = any(marker in haystack for marker in ["不说", "不提", "不声张", "先压", "压下", "到了那一步再说", "只由他一个人先记着"])
            if remembered and withheld:
                return True
        return False

    compact_requirement = re.sub(r"\s+", "", requirement_text)
    for haystack in haystacks:
        if semantic_match(haystack):
            return True
        compact_haystack = re.sub(r"\s+", "", haystack)
        if compact_requirement and (compact_requirement in compact_haystack or compact_haystack in compact_requirement):
            return True
    requirement_tokens = [token for token in tokenize_text(requirement_text) if len(token) >= 2]
    if not requirement_tokens:
        return bool(haystacks)
    for haystack in haystacks:
        if semantic_match(haystack):
            return True
        evidence_tokens = set(tokenize_text(haystack))
        overlap = [token for token in requirement_tokens if token in evidence_tokens]
        if len(overlap) >= min(2, len(requirement_tokens)):
            return True
        if is_generic_requirement(requirement_text) and overlap:
            return True
    return False


def detect_local_tone_drift(task_text: str, draft_text: str, chapter_state_text: str, tracker_bundle: dict[str, Any]) -> list[str]:
    config_text = "\n".join([str(task_text or ""), str(chapter_state_text or "")])
    if not any(marker in config_text for marker in REALISM_TONE_MARKERS):
        return []

    tracker_text = json.dumps(tracker_bundle or {}, ensure_ascii=False) if isinstance(tracker_bundle, dict) else ""
    allowed_text = "\n".join([config_text, tracker_text])
    new_institutions = [marker for marker in INSTITUTION_DRIFT_MARKERS if marker in draft_text and marker not in allowed_text]
    new_spectacles = [marker for marker in SPECTACLE_DRIFT_MARKERS if marker in draft_text and marker not in allowed_text]

    if len(new_spectacles) >= 3 or (new_institutions and len(new_spectacles) >= 2):
        details: list[str] = []
        if new_institutions:
            details.append(f"新增机构/职位：{'、'.join(new_institutions[:3])}")
        if new_spectacles:
            details.append(f"异象词过重：{'、'.join(new_spectacles[:4])}")
        return [f"基调漂移：当前任务要求偏底层现实承接，但正文出现了过重的异象/设定放大（{'；'.join(details)}）。"]
    return []


def detect_local_canon_conflicts(task_text: str, draft_text: str, chapter_state_text: str, tracker_bundle: dict[str, Any]) -> list[str]:
    conflicts: list[str] = []
    revelation_tracker = tracker_bundle.get("revelation_tracker", {}) if isinstance(tracker_bundle, dict) else {}
    artifact_state = tracker_bundle.get("artifact_state", {}) if isinstance(tracker_bundle, dict) else {}
    conflicts.extend(detect_forbidden_reveal_violations(draft_text, revelation_tracker))
    conflicts.extend(detect_artifact_state_conflicts(draft_text, artifact_state))
    if chapter_state_text and ("尚未形成调查念头" in chapter_state_text or "不该主动追问" in chapter_state_text):
        for marker in INVESTIGATION_MARKERS:
            if marker in draft_text:
                conflicts.append(f"chapter_state 明确禁止主动调查，但正文出现了“{marker}”式调查推进。")
                break
    conflicts.extend(detect_local_tone_drift(task_text, draft_text, chapter_state_text, tracker_bundle))
    deduped: list[str] = []
    for item in conflicts:
        text = str(item).strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped[:4]


def build_state_change_evidence(draft_text: str, legacy_result: dict[str, Any] | None) -> dict[str, bool]:
    legacy_result = legacy_result or {}
    information_gain = legacy_result.get("information_gain") or {}
    plot_progress = legacy_result.get("plot_progress") or {}
    character_decision = legacy_result.get("character_decision") or {}
    joined_text = "\n".join(
        [
            draft_text,
            "；".join(normalize_string_list(information_gain.get("new_information_items", []))),
            str(plot_progress.get("progress_reason") or ""),
            str(character_decision.get("decision_detail") or ""),
        ]
    )
    return {
        "物件位置变化": any(marker in joined_text for marker in ARTIFACT_CHANGE_MARKERS),
        "物件状态变化": any(marker in joined_text for marker in ARTIFACT_CHANGE_MARKERS),
        "主角认知变化": bool(normalize_string_list(information_gain.get("new_information_items", []))) or any(marker in joined_text for marker in ["确认", "意识到", "知道", "认出", "怀疑", "想起", "明白"]),
        "关系变化": any(marker in joined_text for marker in RELATIONSHIP_CHANGE_MARKERS),
        "风险等级变化": any(marker in joined_text for marker in RISK_CHANGE_MARKERS),
        "目标变化": any(marker in joined_text for marker in GOAL_CHANGE_MARKERS),
        "行动计划变化": any(marker in joined_text for marker in GOAL_CHANGE_MARKERS),
    }


def state_change_requirement_met(requirement: str, evidence: dict[str, bool], draft_text: str, legacy_result: dict[str, Any] | None) -> bool:
    requirement_text = str(requirement or "").strip()
    if not requirement_text:
        return True
    category_map = [
        ("物件", ["物件位置变化", "物件状态变化"]),
        ("位置", ["物件位置变化"]),
        ("可见性", ["物件状态变化"]),
        ("已知信息", ["主角认知变化"]),
        ("信息", ["主角认知变化"]),
        ("认知", ["主角认知变化"]),
        ("判断", ["主角认知变化"]),
        ("关系", ["关系变化"]),
        ("风险", ["风险等级变化"]),
        ("目标", ["目标变化", "行动计划变化"]),
        ("计划", ["目标变化", "行动计划变化"]),
        ("行动", ["行动计划变化"]),
    ]
    for keyword, fields in category_map:
        if keyword in requirement_text and any(evidence.get(field) for field in fields):
            return True
    joined_evidence = [field for field, matched in evidence.items() if matched]
    return requirement_matches_evidence(requirement_text, joined_evidence, draft_text=draft_text + "\n" + json.dumps(legacy_result or {}, ensure_ascii=False))


def scene_function_to_type(scene_function: str) -> str:
    scene_function = str(scene_function or "").strip()
    if scene_function == "过渡/氛围":
        return "transition"
    return SCENE_FUNCTION_TO_TYPE.get(scene_function, "discovery")


def extract_revision_count(task_id: str) -> int:
    match = re.search(r"-(?:R|RW)(\d+)$", task_id)
    if not match:
        return 0
    return int(match.group(1))


def build_lock_gate_report_path(task_id: str) -> str:
    return f"03_locked/reports/{task_id}_lock_gate_report.json"


def extract_lock_override(task_text: str) -> LockGateOverride:
    reason = (
        extract_markdown_field(task_text, "manual_lock_override")
        or extract_markdown_field(task_text, "lock_gate_override")
        or ""
    ).strip()
    return LockGateOverride(present=bool(reason), reason=reason)


def has_issue(issues: list[ReviewIssue], issue_type: ReviewIssueType, severities: set[ReviewSeverity]) -> list[ReviewIssue]:
    return [item for item in issues if item.type == issue_type and item.severity in severities]


def describe_issues(issues: list[ReviewIssue]) -> str:
    if not issues:
        return "none"
    return "；".join(item.message for item in issues[:3])


def is_scene_purpose_defined(task_text: str) -> tuple[bool, str]:
    goal = (extract_markdown_field(task_text, "goal") or "").strip()
    generic_markers = {"根据 reviewer 结果继续处理当前草稿", "根据当前设定生成草稿", "基于已锁定正文重建 story state。"}
    passed = bool(goal and goal not in generic_markers and len(goal) >= 6)
    return passed, goal or "missing"


def is_chapter_metadata_complete(task_text: str) -> tuple[bool, str]:
    required_fields = ["based_on", "chapter_state", "output_target"]
    missing = [field for field in required_fields if not extract_markdown_field(task_text, field)]
    if missing:
        return False, f"missing: {', '.join(missing)}"
    return True, "complete"


def build_requirement_lock_checks(task_text: str, legacy_result: dict[str, Any] | None) -> list[LockGateCheck]:
    legacy_result = legacy_result or {}
    required_information_gain = extract_markdown_list_field(task_text, "required_information_gain")
    decision_requirement = (extract_markdown_field(task_text, "decision_requirement") or extract_markdown_field(task_text, "required_decision_shift") or "").strip()
    required_state_change = extract_markdown_list_field(task_text, "required_state_change")
    expected_scene_function = (extract_markdown_field(task_text, "scene_function") or "").strip()

    _, draft_text = read_task_path(task_text, "output_target")
    _, based_on_text = read_task_path(task_text, "based_on")
    _, chapter_state_text = read_task_path(task_text, "chapter_state")
    chapter_id = infer_chapter_id(task_text)
    story_state = safe_load_json(ROOT / "03_locked/state/story_state.json")
    previous_scene_id = infer_previous_scene_id(task_text)
    has_runtime_context = bool(draft_text and (based_on_text or chapter_state_text))
    tracker_bundle = (
        load_tracker_bundle(ROOT, chapter_id, chapter_state_text=chapter_state_text, story_state=story_state, upto_scene_id=previous_scene_id)
        if chapter_id and has_runtime_context
        else {}
    )

    information_gain = legacy_result.get("information_gain") or {}
    plot_progress = legacy_result.get("plot_progress") or {}
    character_decision = legacy_result.get("character_decision") or {}
    motif_redundancy = legacy_result.get("motif_redundancy") or {}
    canon_consistency = legacy_result.get("canon_consistency") or {}

    new_information_items = normalize_string_list(information_gain.get("new_information_items", []))
    information_ok = True
    missing_information_reqs: list[str] = []
    if required_information_gain:
        information_ok = bool(new_information_items)
        for item in required_information_gain:
            if requirement_matches_evidence(item, new_information_items, draft_text=draft_text):
                continue
            if is_generic_requirement(item) and new_information_items:
                continue
            missing_information_reqs.append(item)
        information_ok = information_ok and not missing_information_reqs

    decision_ok = True
    decision_detail = str(character_decision.get("decision_detail") or "").strip()
    if decision_requirement:
        decision_ok = bool(character_decision.get("has_decision_or_behavior_shift")) and (
            requirement_matches_evidence(decision_requirement, [decision_detail], draft_text=draft_text)
            or (is_generic_requirement(decision_requirement) and bool(decision_detail))
        )

    state_change_evidence = build_state_change_evidence(draft_text, legacy_result)
    matched_state_changes = [item for item in required_state_change if state_change_requirement_met(item, state_change_evidence, draft_text, legacy_result)]
    state_change_ok = True if not required_state_change else bool(matched_state_changes)

    actual_scene_function = classify_scene_function(draft_text) if draft_text else ""
    scene_function_ok = True
    if expected_scene_function and draft_text:
        scene_function_ok = actual_scene_function == expected_scene_function

    local_canon_conflicts = detect_local_canon_conflicts(task_text, draft_text, chapter_state_text, tracker_bundle) if has_runtime_context else []
    canon_ok = bool(canon_consistency.get("is_consistent", True)) and not local_canon_conflicts

    repeated_motifs = normalize_string_list(motif_redundancy.get("repeated_motifs", []))
    stale_function_motifs = normalize_string_list(motif_redundancy.get("stale_function_motifs", []))
    repeated_same_function_motifs = normalize_string_list(motif_redundancy.get("repeated_same_function_motifs", []))
    consecutive_same_function_motifs = normalize_string_list(motif_redundancy.get("consecutive_same_function_motifs", []))
    redundancy_reason = str(motif_redundancy.get("redundancy_reason") or "").strip()
    motif_high_risk = bool(stale_function_motifs or repeated_same_function_motifs or consecutive_same_function_motifs or (repeated_motifs and not motif_redundancy.get("repetition_has_new_function", True)) or not motif_redundancy.get("same_function_reuse_allowed", True))
    motif_reason_specific = bool(redundancy_reason and redundancy_reason not in GENERIC_REDUNDANCY_REASONS and len(redundancy_reason) >= 8)
    motif_risk_ok = not motif_high_risk or (motif_reason_specific and bool(motif_redundancy.get("repetition_has_new_function", False)) and bool(motif_redundancy.get("same_function_reuse_allowed", False)))

    weak_scene_quota_ok = True
    weak_scene_details = "not a weak-scene lock"
    if has_runtime_context and tracker_bundle:
        chapter_progress = tracker_bundle.get("chapter_progress", {}) if isinstance(tracker_bundle, dict) else {}
        scene_type_control = build_scene_type_control({"chapter_progress": chapter_progress}, scene_type_policy=load_scene_type_policy())
        current_scene_type = scene_function_to_type(actual_scene_function or expected_scene_function)
        disallowed_next_scene_types = normalize_string_list(scene_type_control.get("disallowed_next_scene_types", []))
        weak_scene_quota_ok = current_scene_type not in disallowed_next_scene_types
        weak_scene_details = (
            f"current={current_scene_type}, streak={scene_type_control.get('weak_scene_streak_count')}, disallowed={','.join(disallowed_next_scene_types) or 'none'}"
        )

    return [
        LockGateCheck(
            name="required_information_gain",
            passed=information_ok,
            details=("matched" if information_ok or not required_information_gain else f"missing: {'；'.join(missing_information_reqs[:3])}"),
        ),
        LockGateCheck(
            name="decision_requirement",
            passed=decision_ok,
            details=(decision_detail or decision_requirement or "not specified") if decision_ok else (decision_detail or "missing required decision landing"),
        ),
        LockGateCheck(
            name="required_state_change",
            passed=state_change_ok,
            details=("matched: " + "；".join(matched_state_changes[:3])) if state_change_ok and required_state_change else ("not specified" if not required_state_change else "missing required state change evidence"),
        ),
        LockGateCheck(
            name="scene_function_landed",
            passed=scene_function_ok,
            details=(f"expected={expected_scene_function or 'n/a'} actual={actual_scene_function or 'n/a'}"),
        ),
        LockGateCheck(
            name="chapter_state_alignment",
            passed=canon_ok,
            details=("；".join((local_canon_conflicts or normalize_string_list(canon_consistency.get("consistency_issues", [])))[:3]) or "consistent"),
        ),
        LockGateCheck(
            name="motif_high_risk_explained",
            passed=motif_risk_ok,
            details=redundancy_reason or ("no motif risk" if not motif_high_risk else "high-risk motif reuse without sufficient explanation"),
        ),
        LockGateCheck(
            name="weak_scene_quota",
            passed=weak_scene_quota_ok,
            details=weak_scene_details,
        ),
    ]


def build_structural_lock_checks(legacy_result: dict[str, Any] | None) -> list[LockGateCheck]:
    if not isinstance(legacy_result, dict):
        return []

    information_gain = legacy_result.get("information_gain") or {}
    plot_progress = legacy_result.get("plot_progress") or {}
    character_decision = legacy_result.get("character_decision") or {}
    motif_redundancy = legacy_result.get("motif_redundancy") or {}
    canon_consistency = legacy_result.get("canon_consistency") or {}

    repeated_motifs = [str(item).strip() for item in motif_redundancy.get("repeated_motifs", []) if str(item).strip()]
    repeated_same_function_motifs = [str(item).strip() for item in motif_redundancy.get("repeated_same_function_motifs", []) if str(item).strip()]
    consecutive_same_function_motifs = [str(item).strip() for item in motif_redundancy.get("consecutive_same_function_motifs", []) if str(item).strip()]
    consistency_issues = [str(item).strip() for item in canon_consistency.get("consistency_issues", []) if str(item).strip()]
    state_transition_evidence: list[str] = []
    state_transition_evidence.extend([str(item).strip() for item in information_gain.get("new_information_items", []) if str(item).strip()])
    if str(plot_progress.get("progress_reason") or "").strip() and plot_progress.get("has_plot_progress"):
        state_transition_evidence.append(str(plot_progress.get("progress_reason") or "").strip())
    if str(character_decision.get("decision_detail") or "").strip() and character_decision.get("has_decision_or_behavior_shift"):
        state_transition_evidence.append(str(character_decision.get("decision_detail") or "").strip())

    return [
        LockGateCheck(
            name="information_gain",
            passed=bool(information_gain.get("has_new_information")),
            details="；".join(information_gain.get("new_information_items", [])[:3]) or "missing new information",
        ),
        LockGateCheck(
            name="plot_progress",
            passed=bool(plot_progress.get("has_plot_progress")),
            details=str(plot_progress.get("progress_reason") or "missing plot progress").strip(),
        ),
        LockGateCheck(
            name="character_decision",
            passed=bool(character_decision.get("has_decision_or_behavior_shift")),
            details=str(character_decision.get("decision_detail") or "missing decision or behavior shift").strip(),
        ),
        LockGateCheck(
            name="motif_redundancy",
            passed=(not repeated_motifs or bool(motif_redundancy.get("repetition_has_new_function"))) and (not repeated_same_function_motifs or bool(motif_redundancy.get("same_function_reuse_allowed", True))),
            details=(
                str(motif_redundancy.get("redundancy_reason") or "motif repetition without new function").strip()
                if repeated_motifs
                else (f"same-function streak: {', '.join(consecutive_same_function_motifs[:3])}" if consecutive_same_function_motifs else "no repeated motifs")
            ),
        ),
        LockGateCheck(
            name="canon_consistency",
            passed=bool(canon_consistency.get("is_consistent", True)),
            details="；".join(consistency_issues[:3]) or "consistent",
        ),
        LockGateCheck(
            name="state_transition_evidence",
            passed=bool(state_transition_evidence),
            details="；".join(state_transition_evidence[:3]) or "missing chapter/artifact/revelation state change evidence",
        ),
    ]


def build_lock_gate_report(
    task_text: str,
    review_result: StructuredReviewResult,
    max_revisions: int,
    legacy_result: dict[str, Any] | None = None,
) -> LockGateReport:
    override = extract_lock_override(task_text)
    task_id = review_result.task_id
    timeline_issues = has_issue(review_result.issues, ReviewIssueType.timeline, {ReviewSeverity.critical})
    continuity_issues = has_issue(review_result.issues, ReviewIssueType.continuity, {ReviewSeverity.critical})
    pov_issues = has_issue(review_result.issues, ReviewIssueType.pov, {ReviewSeverity.high, ReviewSeverity.critical})

    revision_count = extract_revision_count(task_id)
    within_policy = revision_count <= max_revisions or override.present
    scene_purpose_ok, scene_purpose_details = is_scene_purpose_defined(task_text)
    metadata_ok, metadata_details = is_chapter_metadata_complete(task_text)

    checks = [
        LockGateCheck(name="timeline_blockers", passed=not timeline_issues, details=describe_issues(timeline_issues)),
        LockGateCheck(name="continuity_blockers", passed=not continuity_issues, details=describe_issues(continuity_issues)),
        LockGateCheck(name="pov_blockers", passed=not pov_issues, details=describe_issues(pov_issues)),
        LockGateCheck(
            name="revise_policy",
            passed=within_policy,
            details=(
                f"revision_count={revision_count}, max={max_revisions}, override={override.reason}"
                if override.present
                else f"revision_count={revision_count}, max={max_revisions}"
            ),
        ),
        LockGateCheck(name="scene_purpose_defined", passed=scene_purpose_ok, details=scene_purpose_details),
        LockGateCheck(name="chapter_metadata_complete", passed=metadata_ok, details=metadata_details),
    ]
    checks.extend(build_structural_lock_checks(legacy_result))
    checks.extend(build_requirement_lock_checks(task_text, legacy_result))

    return LockGateReport(
        task_id=task_id,
        passed=all(check.passed for check in checks),
        checks=checks,
        policy_override=override,
    )


def save_lock_gate_report(root: Path, report: LockGateReport) -> str:
    rel_path = build_lock_gate_report_path(report.task_id)
    report.save(root / rel_path)
    return rel_path


def apply_lock_gate(task_text: str, reviewer_result: dict[str, Any], max_revisions: int) -> tuple[dict[str, Any], LockGateReport]:
    structured_review = build_structured_review_result(reviewer_result)
    report = build_lock_gate_report(task_text, structured_review, max_revisions, legacy_result=reviewer_result)

    if reviewer_result.get("verdict") != "lock" or report.passed:
        return reviewer_result, report

    failed_details = [f"{check.name}: {check.details}" for check in report.checks if not check.passed]
    updated = dict(reviewer_result)
    updated["verdict"] = "revise"
    updated["task_goal_fulfilled"] = False
    updated["recommended_next_step"] = "create_revision_task"

    major_issues = list(updated.get("major_issues", []))
    gate_issue = f"锁定闸门未通过：{'；'.join(failed_details)}"
    if gate_issue not in major_issues:
        major_issues.insert(0, gate_issue)
    updated["major_issues"] = major_issues
    updated["summary"] = gate_issue

    repaired_structured = build_structured_review_result(updated)
    repair_plan = build_repair_plan(repaired_structured)
    if repair_plan.mode == RepairMode.full_redraft:
        updated["recommended_next_step"] = "rewrite_scene"
        updated["verdict"] = "rewrite"
    return updated, report
