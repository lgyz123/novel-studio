import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from review_models import ReviewStatus, StructuredReviewResult


class RevisionRound(BaseModel):
    round: int
    task_id: str = Field(min_length=1)
    draft_id: str = Field(min_length=1)
    issues: list[str] = Field(default_factory=list)
    issues_fixed: list[str] = Field(default_factory=list)
    decision: str = Field(min_length=1)


class RevisionLineage(BaseModel):
    task_id: str = Field(min_length=1)
    revisions: list[RevisionRound] = Field(default_factory=list)
    recurring_issue_types: list[str] = Field(default_factory=list)
    escalate_after: int = 5
    escalation_reason: str = ""

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
    def from_dict(cls, data: dict[str, Any]) -> "RevisionLineage":
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls.parse_obj(data)

    @classmethod
    def load(cls, path: Path) -> "RevisionLineage":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


def normalize_base_task_id(task_id: str) -> str:
    normalized = task_id.strip()
    while True:
        updated = re.sub(r"-(?:R\d+|RW\d+)$", "", normalized)
        if updated == normalized:
            return normalized
        normalized = updated


def build_revision_lineage_path(task_id: str) -> str:
    return f"02_working/reviews/{normalize_base_task_id(task_id)}_revision_lineage.json"


def load_revision_lineage(root: Path, task_id: str, escalate_after: int) -> RevisionLineage:
    rel_path = build_revision_lineage_path(task_id)
    path = root / rel_path
    if not path.exists():
        return RevisionLineage(task_id=normalize_base_task_id(task_id), escalate_after=escalate_after)
    lineage = RevisionLineage.load(path)
    lineage.escalate_after = escalate_after
    return lineage


def unique_issue_types(review_result: StructuredReviewResult) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for issue in review_result.issues:
        issue_type = issue.type.value
        if issue_type in seen:
            continue
        seen.add(issue_type)
        result.append(issue_type)
    return result


def build_draft_id(draft_file: str) -> str:
    return Path(draft_file).stem


def compute_recurring_issue_types(revisions: list[RevisionRound]) -> list[str]:
    counts: dict[str, int] = {}
    for revision in revisions:
        for issue_type in set(revision.issues):
            counts[issue_type] = counts.get(issue_type, 0) + 1
    return sorted([issue_type for issue_type, count in counts.items() if count >= 2])


def compute_persistent_issue_types(revisions: list[RevisionRound], lookback: int = 3) -> list[str]:
    if len(revisions) < lookback:
        return []
    recent = revisions[-lookback:]
    issue_sets = [set(item.issues) for item in recent if item.issues]
    if len(issue_sets) < lookback:
        return []
    persistent = set.intersection(*issue_sets)
    return sorted(persistent)


def derive_escalation_reason(lineage: RevisionLineage) -> str:
    if not lineage.revisions:
        return ""

    latest = lineage.revisions[-1]
    if latest.decision == ReviewStatus.lock.value:
        return ""

    if len(lineage.revisions) >= lineage.escalate_after:
        return f"已达到修订阈值 {lineage.escalate_after} 轮，建议人工介入。"

    persistent = compute_persistent_issue_types(lineage.revisions)
    if persistent and not latest.issues_fixed:
        return f"重复问题未收敛：{', '.join(persistent)}"

    return ""


def should_trigger_manual_intervention(lineage: RevisionLineage) -> bool:
    return bool(lineage.escalation_reason)


def append_revision_lineage(
    root: Path,
    review_result: StructuredReviewResult,
    draft_file: str,
    escalate_after: int,
) -> tuple[RevisionLineage, str]:
    lineage = load_revision_lineage(root, review_result.task_id, escalate_after)
    issues = unique_issue_types(review_result)
    previous_issues = lineage.revisions[-1].issues if lineage.revisions else []
    issues_fixed = [issue for issue in previous_issues if issue not in issues]

    revision_round = RevisionRound(
        round=len(lineage.revisions) + 1,
        task_id=review_result.task_id,
        draft_id=build_draft_id(draft_file),
        issues=issues,
        issues_fixed=issues_fixed,
        decision=review_result.status.value,
    )

    if lineage.revisions and lineage.revisions[-1].task_id == review_result.task_id:
        lineage.revisions[-1] = revision_round
    else:
        lineage.revisions.append(revision_round)

    lineage.recurring_issue_types = compute_recurring_issue_types(lineage.revisions)
    lineage.escalation_reason = derive_escalation_reason(lineage)

    rel_path = build_revision_lineage_path(review_result.task_id)
    lineage.save(root / rel_path)
    return lineage, rel_path


def build_revision_lineage_summary(lineage: RevisionLineage) -> str:
    if not lineage.revisions:
        return "revision lineage：暂无记录"

    latest = lineage.revisions[-1]
    recurring = ", ".join(lineage.recurring_issue_types) if lineage.recurring_issue_types else "none"
    fixed = ", ".join(latest.issues_fixed) if latest.issues_fixed else "none"
    return (
        f"revision lineage：round={latest.round} decision={latest.decision} "
        f"issues={','.join(latest.issues) or 'none'} fixed={fixed} recurring={recurring}"
    )
