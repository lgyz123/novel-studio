import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import app.main as main_module
from app.review_models import build_structured_review_result, load_structured_review_result, save_repair_plan, save_structured_review_result
from app.revision_lineage import (
    append_revision_lineage,
    build_revision_lineage_summary,
    load_revision_lineage,
    normalize_base_task_id,
    should_trigger_manual_intervention,
)


class RevisionLineageTest(unittest.TestCase):
    def test_append_revision_lineage_tracks_rounds_and_fixed_issues(self) -> None:
        round1 = build_structured_review_result(
            {
                "task_id": "scene_050-R1",
                "verdict": "revise",
                "summary": "需要继续修订。",
                "major_issues": ["存在时间线问题。", "文体略显松散。"],
                "minor_issues": [],
            }
        )
        round2 = build_structured_review_result(
            {
                "task_id": "scene_050-R2",
                "verdict": "revise",
                "summary": "只剩文体问题。",
                "major_issues": [],
                "minor_issues": ["文体略显松散。"],
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            lineage, rel_path = append_revision_lineage(root, round1, "02_working/drafts/ch01_scene50_v2.md", escalate_after=5)
            self.assertEqual(rel_path, "02_working/reviews/scene_050_revision_lineage.json")
            self.assertEqual(lineage.revisions[0].round, 1)
            self.assertIn("timeline", lineage.revisions[0].issues)
            self.assertIn("style", lineage.revisions[0].issues)

            lineage, _ = append_revision_lineage(root, round2, "02_working/drafts/ch01_scene50_v3.md", escalate_after=5)
            self.assertEqual(lineage.revisions[1].round, 2)
            self.assertEqual(lineage.revisions[1].issues_fixed, ["timeline"])
            self.assertEqual(lineage.recurring_issue_types, ["style"])
            self.assertIn("recurring=style", build_revision_lineage_summary(lineage))

    def test_lineage_triggers_escalation_for_persistent_recurring_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for task_id in ("scene_051-R1", "scene_051-R2", "scene_051-R3"):
                structured = build_structured_review_result(
                    {
                        "task_id": task_id,
                        "verdict": "revise",
                        "summary": "重复风格问题未解决。",
                        "major_issues": [],
                        "minor_issues": ["文体略显松散。"],
                    }
                )
                lineage, _ = append_revision_lineage(root, structured, f"02_working/drafts/{task_id}.md", escalate_after=5)

            self.assertTrue(should_trigger_manual_intervention(lineage))
            self.assertIn("style", lineage.recurring_issue_types)
            self.assertIn("重复问题未收敛", lineage.escalation_reason)

    def test_route_review_result_creates_manual_intervention_on_lineage_escalation(self) -> None:
        task_text = """# task_id
scene_052-R3

# goal
继续修订当前 scene。

# based_on
02_working/drafts/ch01_scene52_v3.md

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/ch01_scene52_v4.md
"""
        reviewer_result = {
            "task_id": "scene_052-R3",
            "verdict": "revise",
            "summary": "重复问题未收敛：style",
            "major_issues": ["重复问题未收敛：style"],
            "minor_issues": [],
            "force_manual_intervention_reason": "重复问题未收敛：style",
        }
        config = {"paths": {"working_dir": "02_working", "inputs_dir": "01_inputs"}, "generation": {"max_auto_revisions": 5}}

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                save_structured_review_result(root, reviewer_result)
                created = main_module.route_review_result(config, task_text, "02_working/drafts/ch01_scene52_v3.md", reviewer_result)
                self.assertIn("manual_intervention_file", created)
                self.assertTrue((root / created["manual_intervention_file"]).exists())
                structured = load_structured_review_result(root, "scene_052-R3")
                self.assertEqual(structured.status.value, "manual_intervention")
            finally:
                main_module.ROOT = previous_root

    def test_manual_intervention_document_includes_structured_context(self) -> None:
        task_text = """# task_id
scene_053-R3

# goal
继续修订当前 scene。

# based_on
02_working/drafts/ch01_scene53_v3.md

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/ch01_scene53_v4.md
"""
        reviewer_result = {
            "task_id": "scene_053-R3",
            "verdict": "revise",
            "summary": "重复问题未收敛：style",
            "major_issues": ["文体略显松散，关键段落缺少压缩。"],
            "minor_issues": ["第2段解释偏多。"],
            "force_manual_intervention_reason": "重复问题未收敛：style",
        }
        config = {"paths": {"working_dir": "02_working", "inputs_dir": "01_inputs"}, "generation": {"max_auto_revisions": 5}}

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                for task_id in ("scene_053-R1", "scene_053-R2"):
                    prior = build_structured_review_result(
                        {
                            "task_id": task_id,
                            "verdict": "revise",
                            "summary": "文体问题仍未解决。",
                            "major_issues": [],
                            "minor_issues": ["文体略显松散。"],
                        }
                    )
                    append_revision_lineage(root, prior, f"02_working/drafts/{task_id}.md", escalate_after=5)

                save_structured_review_result(root, reviewer_result)
                structured = load_structured_review_result(root, "scene_053-R3")
                save_repair_plan(root, structured)
                append_revision_lineage(root, structured, "02_working/drafts/ch01_scene53_v3.md", escalate_after=5)

                created = main_module.route_review_result(config, task_text, "02_working/drafts/ch01_scene53_v3.md", reviewer_result)
                manual_path = root / created["manual_intervention_file"]
                content = manual_path.read_text(encoding="utf-8")

                self.assertIn("## 当前状态", content)
                self.assertIn("## 为什么自动化停止", content)
                self.assertIn("## 当前未解决的关键问题", content)
                self.assertIn("ISSUE-001", content)
                self.assertIn("scene_053-R3_repair_plan.json", content)
                self.assertIn("scene_053_revision_lineage.json", content)
                self.assertIn("重复问题类型：style", content)
                self.assertIn("## 下一次重试可直接使用的提示词", content)
                self.assertIn("修订模式：`partial_redraft`", content)
            finally:
                main_module.ROOT = previous_root

    def test_normalize_base_task_id(self) -> None:
        self.assertEqual(normalize_base_task_id("scene_012-R3"), "scene_012")
        self.assertEqual(normalize_base_task_id("scene_012-RW1"), "scene_012")
        self.assertEqual(normalize_base_task_id("scene_012-RW1-RW2"), "scene_012")


if __name__ == "__main__":
    unittest.main()
