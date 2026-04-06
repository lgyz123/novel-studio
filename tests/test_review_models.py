import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.main import build_generated_task_content, build_writer_user_prompt
from app.review_models import (
    RepairMode,
    ReviewIssue,
    ReviewScope,
    ReviewSeverity,
    ReviewStatus,
    StructuredReviewResult,
    build_repair_plan,
    build_review_result_path,
    build_structured_review_result,
    load_structured_review_result,
    load_repair_plan,
    save_repair_plan,
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

    def test_repair_plan_prefers_local_fix_for_small_local_issues(self) -> None:
        legacy_result = {
            "task_id": "scene_040",
            "verdict": "revise",
            "summary": "整体方向正确，仅有局部润色问题。",
            "major_issues": [],
            "minor_issues": ["第2段说明略显重复，需精简。", "第7段视角稍松，可再收紧。"],
        }
        structured = build_structured_review_result(legacy_result)
        plan = build_repair_plan(structured)

        self.assertEqual(plan.mode, RepairMode.local_fix)
        self.assertEqual(len(plan.actions), 2)
        self.assertEqual(plan.actions[0].issue_id, "ISSUE-001")
        self.assertTrue(plan.actions[0].instruction)

    def test_repair_plan_escalates_to_full_redraft_for_blocking_issue(self) -> None:
        legacy_result = {
            "task_id": "scene_041",
            "verdict": "revise",
            "summary": "核心推进未完成，需要重构当前 scene。",
            "major_issues": ["核心推进未完成，导致本场 scene 功能失效。"],
            "minor_issues": [],
        }
        structured = build_structured_review_result(legacy_result)
        plan = build_repair_plan(structured)

        self.assertEqual(plan.mode, RepairMode.full_redraft)
        self.assertEqual(plan.actions[0].action, "rewrite_local_block")

    def test_repair_plan_save_and_load(self) -> None:
        legacy_result = {
            "task_id": "scene_042",
            "verdict": "revise",
            "summary": "需要处理局部问题。",
            "major_issues": ["第4段动作牵引不够明确。"],
            "minor_issues": ["第7段解释略重复。"],
        }
        structured = build_structured_review_result(legacy_result)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            rel_path = save_repair_plan(root, structured)
            loaded = load_repair_plan(root, "scene_042")

            self.assertEqual(rel_path, "02_working/reviews/scene_042_repair_plan.json")
            self.assertEqual(loaded.task_id, "scene_042")
            self.assertGreaterEqual(len(loaded.actions), 1)

    def test_generated_revision_task_includes_repair_plan_metadata(self) -> None:
        legacy_result = {
            "task_id": "scene_043",
            "verdict": "revise",
            "summary": "需要处理局部动作与冗余。",
            "major_issues": ["第4段动作牵引不够明确。"],
            "minor_issues": ["第7段解释略重复。"],
        }
        structured = build_structured_review_result(legacy_result)
        task_text = """# task_id
scene_043

# goal
延续当前 scene。

# constraints
- 保持单视角

# output_target
02_working/drafts/ch01_scene10.md
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            save_repair_plan(root, structured)

            import app.main as main_module

            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                content = build_generated_task_content(
                    task_text,
                    {"summary": legacy_result["summary"], "major_issues": legacy_result["major_issues"], "minor_issues": legacy_result["minor_issues"]},
                    "02_working/drafts/ch01_scene10.md",
                    "revise",
                )
            finally:
                main_module.ROOT = previous_root

            self.assertIn("# repair_mode", content)
            self.assertIn("partial_redraft", content)
            self.assertIn("# repair_plan", content)
            self.assertIn("scene_043_repair_plan.json", content)

    def test_writer_prompt_includes_repair_plan_guidance(self) -> None:
        legacy_result = {
            "task_id": "scene_044",
            "verdict": "revise",
            "summary": "处理局部 POV 与重复问题。",
            "major_issues": [],
            "minor_issues": ["第2段视角略松，需要收紧。", "第6段解释重复，需精简。"],
        }
        structured = build_structured_review_result(legacy_result)
        task_text = """# task_id
scene_044

# goal
修订当前 scene。

# repair_mode
local_fix

# repair_plan
02_working/reviews/scene_044_repair_plan.json
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            save_repair_plan(root, structured)

            import app.main as main_module

            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                prompt = build_writer_user_prompt(
                    task_text,
                    "上下文内容",
                    {"task_id": "scene_044", "goal": "修订当前 scene", "draft_file": "02_working/drafts/scene_044.md"},
                )
            finally:
                main_module.ROOT = previous_root

            self.assertIn("【修订执行计划】", prompt)
            self.assertIn("repair_mode: local_fix", prompt)
            self.assertIn("scene_044_repair_plan.json", prompt)
            self.assertIn("本次是局部修补，不要推倒整场重写", prompt)
            self.assertIn("必须优先处理的修订动作", prompt)


if __name__ == "__main__":
    unittest.main()
