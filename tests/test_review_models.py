import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.review_models import (
    ReviewIssue,
    ReviewScope,
    ReviewSeverity,
    ReviewStatus,
    StructuredReviewResult,
    build_review_result_path,
    build_structured_review_result,
    load_structured_review_result,
    save_structured_review_result,
    update_structured_review_status,
)


class ReviewModelsTest(unittest.TestCase):
    def test_invalid_issue_category_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ReviewIssue(
                id="ISSUE-001",
                type="bad_type",
                severity="high",
                scope="scene",
                target="scene_001",
                message="bad",
                suggested_action="rewrite_local",
            )

        with self.assertRaises(ValidationError):
            ReviewIssue(
                id="ISSUE-001",
                type="style",
                severity="bad_severity",
                scope="scene",
                target="scene_001",
                message="bad",
                suggested_action="rewrite_local",
            )

    def test_save_and_load_structured_review_result(self) -> None:
        legacy_result = {
            "task_id": "scene_012_draft_03",
            "verdict": "revise",
            "summary": "当前方向正确，但动作牵引仍不够明确。",
            "major_issues": ["动作牵引不够明确，导致场景功能未完全成立。"],
            "minor_issues": ["部分句子略显冗长，需精简。"],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            rel_path = save_structured_review_result(root, legacy_result)
            self.assertEqual(rel_path, build_review_result_path("scene_012_draft_03"))

            loaded = load_structured_review_result(root, "scene_012_draft_03")
            self.assertEqual(loaded.status, ReviewStatus.revise)
            self.assertEqual(len(loaded.issues), 2)
            self.assertEqual(loaded.issues[0].severity, ReviewSeverity.high)
            self.assertEqual(loaded.issues[0].scope, ReviewScope.scene)
            self.assertEqual(loaded.issues[0].message, "动作牵引不够明确，导致场景功能未完全成立。")

    def test_manual_intervention_status_update(self) -> None:
        legacy_result = {
            "task_id": "scene_020-R5",
            "verdict": "revise",
            "summary": "仍需继续修订。",
            "major_issues": ["核心推进不足。"],
            "minor_issues": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            save_structured_review_result(root, legacy_result)
            update_structured_review_status(root, "scene_020-R5", ReviewStatus.manual_intervention, "已达自动修订上限，转人工介入。")
            loaded = load_structured_review_result(root, "scene_020-R5")
            self.assertEqual(loaded.status, ReviewStatus.manual_intervention)
            self.assertEqual(loaded.summary, "已达自动修订上限，转人工介入。")
            self.assertEqual(loaded.decision_reason, "已达自动修订上限，转人工介入。")

    def test_downstream_can_read_status_and_issues(self) -> None:
        legacy_result = {
            "task_id": "scene_030",
            "verdict": "lock",
            "summary": "当前 scene 已满足锁定条件。",
            "major_issues": [],
            "minor_issues": ["个别句子还能再压一压。"],
        }
        structured = build_structured_review_result(legacy_result)

        self.assertEqual(structured.status, ReviewStatus.lock)
        self.assertEqual(structured.issues[0].message, "个别句子还能再压一压。")
        self.assertEqual(structured.issues[0].severity, ReviewSeverity.medium)


if __name__ == "__main__":
    unittest.main()
