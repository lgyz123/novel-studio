import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, validator


class ReviewStatus(str, Enum):
    lock = "lock"
    revise = "revise"
    rewrite = "rewrite"
    manual_intervention = "manual_intervention"


class ReviewIssueType(str, Enum):
    continuity = "continuity"
    timeline = "timeline"
    pov = "pov"
    knowledge = "knowledge"
    style = "style"
    scene_purpose = "scene_purpose"
    foreshadowing = "foreshadowing"
    redundancy = "redundancy"


class ReviewSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ReviewScope(str, Enum):
    local = "local"
    scene = "scene"
    chapter = "chapter"
    global_ = "global"

    @classmethod
    def from_value(cls, value: str) -> "ReviewScope":
        if value == "global":
            return cls.global_
        return cls(value)

    def to_json_value(self) -> str:
        return "global" if self is ReviewScope.global_ else self.value


class ReviewIssue(BaseModel):
    id: str = Field(min_length=1)
    type: ReviewIssueType
    severity: ReviewSeverity
    scope: ReviewScope
    target: str = Field(min_length=1)
    message: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)

    @validator("id")
    def validate_issue_id(cls, value: str) -> str:
        if not re.fullmatch(r"ISSUE-\d{3}", value):
            raise ValueError("issue id must match ISSUE-001 format")
        return value


class StructuredReviewResult(BaseModel):
    task_id: str = Field(min_length=1)
    status: ReviewStatus
    summary: str = Field(min_length=1)
    issues: list[ReviewIssue] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    decision_reason: str = Field(min_length=1)

    @validator("strengths", each_item=True)
    def validate_strengths(cls, value: str) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("strengths cannot contain empty strings")
        return text

    def to_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            data = self.model_dump()
        else:
            data = self.dict()
        for item in data.get("issues", []):
            scope_value = item.get("scope")
            if scope_value == "global_":
                item["scope"] = "global"
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StructuredReviewResult":
        normalized = dict(data)
        issues = []
        for item in normalized.get("issues", []):
            issue = dict(item)
            if issue.get("scope") == "global_":
                issue["scope"] = "global"
            issues.append(issue)
        normalized["issues"] = issues
        if hasattr(cls, "model_validate"):
            return cls.model_validate(normalized)
        return cls.parse_obj(normalized)

    @classmethod
    def load(cls, path: Path) -> "StructuredReviewResult":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


class RepairMode(str, Enum):
    local_fix = "local_fix"
    partial_redraft = "partial_redraft"
    full_redraft = "full_redraft"


class RepairAction(BaseModel):
    target: str = Field(min_length=1)
    issue_id: str = Field(min_length=1)
    action: str = Field(min_length=1)
    instruction: str = Field(min_length=1)


class RepairPlan(BaseModel):
    task_id: str = Field(min_length=1)
    mode: RepairMode
    actions: list[RepairAction] = Field(default_factory=list)

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
    def from_dict(cls, data: dict[str, Any]) -> "RepairPlan":
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls.parse_obj(data)

    @classmethod
    def load(cls, path: Path) -> "RepairPlan":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


TYPE_RULES: list[tuple[ReviewIssueType, tuple[str, ...]]] = [
    (ReviewIssueType.pov, ("视角", "pov", "单视角", "视角漂移")),
    (ReviewIssueType.timeline, ("时序", "时间线", "timeline", "前后不一", "前后矛盾")),
    (ReviewIssueType.knowledge, ("认知", "知道", "knowledge", "信息差", "不该知道")),
    (ReviewIssueType.style, ("文体", "说明腔", "剧本体", "修辞", "冗长", "篇幅", "语言", "too short", "too long")),
    (ReviewIssueType.foreshadowing, ("伏笔", "foreshadow", "钩子", "悬念")),
    (ReviewIssueType.redundancy, ("重复", "冗余", "重复了", "意象重复", "太满")),
    (ReviewIssueType.continuity, ("承接", "前文", "连续", "衔接", "scene0", "chapter_state", "前场")),
]


def build_review_result_path(task_id: str) -> str:
    return f"02_working/reviews/{task_id}_review_result.json"


def build_repair_plan_path(task_id: str) -> str:
    return f"02_working/reviews/{task_id}_repair_plan.json"


def map_verdict_to_status(verdict: str) -> ReviewStatus:
    normalized = str(verdict or "revise").strip().lower()
    if normalized == "lock":
        return ReviewStatus.lock
    if normalized == "rewrite":
        return ReviewStatus.rewrite
    if normalized == "manual_intervention":
        return ReviewStatus.manual_intervention
    return ReviewStatus.revise


def classify_issue_type(message: str) -> ReviewIssueType:
    lower_text = message.lower()
    for issue_type, markers in TYPE_RULES:
        if any(marker.lower() in lower_text for marker in markers):
            return issue_type
    return ReviewIssueType.scene_purpose


def classify_issue_severity(message: str, bucket: str) -> ReviewSeverity:
    lower_text = message.lower()
    critical_markers = ("严重", "核心", "失效", "越界", "方向错误", "缺失", "missing", "fails", "does not meet")
    high_markers = ("未完成", "不足", "不够", "偏弱", "不明确", "too short", "not in", "缺乏")
    low_markers = ("略", "可再", "轻微", "精简", "润色")

    if bucket == "major" and any(marker in lower_text for marker in critical_markers):
        return ReviewSeverity.critical
    if bucket == "major":
        if any(marker in lower_text for marker in high_markers):
            return ReviewSeverity.high
        return ReviewSeverity.high
    if any(marker in lower_text for marker in low_markers):
        return ReviewSeverity.low
    return ReviewSeverity.medium


def classify_issue_scope(message: str) -> ReviewScope:
    lower_text = message.lower()
    if any(marker in lower_text for marker in ("paragraph", "para", "段", "句", "局部")):
        return ReviewScope.local
    if any(marker in lower_text for marker in ("章节", "chapter", "节奏", "本章")):
        return ReviewScope.chapter
    if any(marker in lower_text for marker in ("全局", "global", "设定", "世界观", "主线")):
        return ReviewScope.global_
    return ReviewScope.scene


def infer_issue_target(task_id: str, message: str) -> str:
    paragraph_match = re.search(r"(?:paragraph|para|第)(\d+)(?:段)?", message, re.IGNORECASE)
    if paragraph_match:
        return f"{task_id}_para_{paragraph_match.group(1)}"
    return task_id


def infer_suggested_action(issue_type: ReviewIssueType, severity: ReviewSeverity, scope: ReviewScope) -> str:
    if scope == ReviewScope.local:
        if issue_type == ReviewIssueType.redundancy:
            return "trim_local"
        if issue_type == ReviewIssueType.pov:
            return "tighten_pov"
        if issue_type == ReviewIssueType.foreshadowing:
            return "adjust_foreshadowing"
        return "rewrite_local"

    if severity in {ReviewSeverity.critical, ReviewSeverity.high} and issue_type in {
        ReviewIssueType.scene_purpose,
        ReviewIssueType.continuity,
        ReviewIssueType.timeline,
    }:
        return "rewrite_scene"
    if issue_type == ReviewIssueType.redundancy:
        return "trim_local"
    if issue_type == ReviewIssueType.style:
        return "rewrite_local"
    if issue_type == ReviewIssueType.pov:
        return "tighten_pov"
    if issue_type == ReviewIssueType.foreshadowing:
        return "adjust_foreshadowing"
    return "rewrite_local"


def build_repair_instruction(issue: ReviewIssue) -> str:
    action_templates = {
        "rewrite_scene": "围绕该问题重写相关场段，确保核心目标与约束重新成立。",
        "rewrite_local": "在对应位置局部改写，直接修复该问题，不扩散到整场。",
        "tighten_pov": "收紧视角，恢复贴近主角的叙述边界，删除越界信息。",
        "adjust_foreshadowing": "压低伏笔力度，只保留本场需要的轻推信息。",
        "trim_local": "删去重复解释或过满表达，保留必要动作与信息。",
    }
    base = action_templates.get(issue.suggested_action, "根据该问题执行局部修补，避免不必要的整场重写。")
    return f"{base}问题：{issue.message}"


def map_issue_to_repair_action(issue: ReviewIssue) -> RepairAction:
    action_map = {
        "rewrite_scene": "rewrite_local_block",
        "rewrite_local": "rewrite_local",
        "tighten_pov": "rewrite_local",
        "adjust_foreshadowing": "adjust_foreshadowing",
        "trim_local": "tighten",
    }
    return RepairAction(
        target=issue.target,
        issue_id=issue.id,
        action=action_map.get(issue.suggested_action, issue.suggested_action),
        instruction=build_repair_instruction(issue),
    )


def choose_repair_mode(review_result: StructuredReviewResult) -> RepairMode:
    issues = review_result.issues
    if review_result.status == ReviewStatus.rewrite:
        return RepairMode.full_redraft
    if not issues:
        return RepairMode.local_fix

    if any(
        issue.severity == ReviewSeverity.critical
        or (issue.severity == ReviewSeverity.high and issue.scope in {ReviewScope.chapter, ReviewScope.global_, ReviewScope.scene})
        or issue.suggested_action == "rewrite_scene"
        for issue in issues
    ):
        return RepairMode.full_redraft

    if all(
        issue.scope == ReviewScope.local
        and issue.severity in {ReviewSeverity.low, ReviewSeverity.medium}
        and issue.suggested_action != "rewrite_scene"
        for issue in issues
    ):
        return RepairMode.local_fix

    return RepairMode.partial_redraft


def build_repair_plan(review_result: StructuredReviewResult) -> RepairPlan:
    actions = [map_issue_to_repair_action(issue) for issue in review_result.issues]
    return RepairPlan(
        task_id=review_result.task_id,
        mode=choose_repair_mode(review_result),
        actions=actions,
    )


def build_issue(issue_id: int, task_id: str, message: str, bucket: str) -> ReviewIssue:
    issue_type = classify_issue_type(message)
    severity = classify_issue_severity(message, bucket)
    scope = classify_issue_scope(message)
    return ReviewIssue(
        id=f"ISSUE-{issue_id:03d}",
        type=issue_type,
        severity=severity,
        scope=scope,
        target=infer_issue_target(task_id, message),
        message=message.strip(),
        suggested_action=infer_suggested_action(issue_type, severity, scope),
    )


def infer_strengths(status: ReviewStatus, summary: str, minor_issues: list[str]) -> list[str]:
    strengths: list[str] = []
    summary = summary.strip()

    if status == ReviewStatus.lock:
        strengths.append(summary or "本场已满足锁定条件。")
    elif summary and any(marker in summary for marker in ("方向正确", "基本正确", "约束基本遵守")):
        strengths.append(summary)

    if not strengths and minor_issues:
        strengths.append("草稿整体方向可用，问题主要集中在局部完成度。")

    return strengths[:3]


def build_decision_reason(status: ReviewStatus, summary: str, issues: list[ReviewIssue]) -> str:
    if summary.strip():
        return summary.strip()
    if status == ReviewStatus.lock:
        return "无阻塞性问题，当前 scene 可直接锁定。"
    if issues:
        return f"存在 {len(issues)} 个待处理问题，需要继续修订。"
    return "当前 review 已完成结构化落盘。"


def build_structured_review_result(legacy_result: dict[str, Any]) -> StructuredReviewResult:
    task_id = str(legacy_result.get("task_id") or "unknown-task").strip() or "unknown-task"
    summary = str(legacy_result.get("summary") or "审稿已完成。")
    status = map_verdict_to_status(str(legacy_result.get("verdict") or "revise"))

    issues: list[ReviewIssue] = []
    issue_index = 1
    for bucket_name, bucket in (("major", legacy_result.get("major_issues", [])), ("minor", legacy_result.get("minor_issues", []))):
        for raw_message in bucket or []:
            message = str(raw_message).strip()
            if not message:
                continue
            issues.append(build_issue(issue_index, task_id, message, bucket_name))
            issue_index += 1

    strengths = infer_strengths(status, summary, [str(item).strip() for item in legacy_result.get("minor_issues", []) if str(item).strip()])
    return StructuredReviewResult(
        task_id=task_id,
        status=status,
        summary=summary,
        issues=issues,
        strengths=strengths,
        decision_reason=build_decision_reason(status, summary, issues),
    )


def save_structured_review_result(root: Path, legacy_result: dict[str, Any]) -> str:
    structured = build_structured_review_result(legacy_result)
    rel_path = build_review_result_path(structured.task_id)
    structured.save(root / rel_path)
    return rel_path


def load_structured_review_result(root: Path, task_id: str) -> StructuredReviewResult:
    return StructuredReviewResult.load(root / build_review_result_path(task_id))


def save_repair_plan(root: Path, review_result: StructuredReviewResult) -> str:
    plan = build_repair_plan(review_result)
    rel_path = build_repair_plan_path(review_result.task_id)
    plan.save(root / rel_path)
    return rel_path


def load_repair_plan(root: Path, task_id: str) -> RepairPlan:
    return RepairPlan.load(root / build_repair_plan_path(task_id))


def update_structured_review_status(root: Path, task_id: str, status: ReviewStatus, decision_reason: str | None = None) -> str:
    path = root / build_review_result_path(task_id)
    result = StructuredReviewResult.load(path)
    result.status = status
    if decision_reason:
        result.decision_reason = decision_reason.strip()
        result.summary = decision_reason.strip()
    result.save(path)
    return build_review_result_path(task_id)
