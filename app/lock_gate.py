import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

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


def extract_revision_count(task_id: str) -> int:
    match = re.search(r"-R(\d+)$", task_id)
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


def build_lock_gate_report(task_text: str, review_result: StructuredReviewResult, max_revisions: int) -> LockGateReport:
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
    report = build_lock_gate_report(task_text, structured_review, max_revisions)

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
