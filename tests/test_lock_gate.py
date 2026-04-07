import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.lock_gate import apply_lock_gate, build_lock_gate_report, save_lock_gate_report
from app.review_models import build_structured_review_result


BASE_TASK = """# task_id
scene_012_draft_05

# goal
承接上一场，完成本场唯一推进目标。

# based_on
03_locked/chapters/ch01_scene11.md

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/ch01_scene12.md
"""


class LockGateTest(unittest.TestCase):
    def test_lock_gate_passes_clean_lock(self) -> None:
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "当前 scene 满足锁定条件。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": True, "new_information_items": ["确认了尸体腰间少了一枚铜钱。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "主角因此改变了交差顺序。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他先把铜钱藏起，没有立刻交差。"},
            "motif_redundancy": {"repeated_motifs": ["红绳"], "repetition_has_new_function": True, "redundancy_reason": "红绳这次触发了新的现实动作。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }
        structured = build_structured_review_result(reviewer_result)
        report = build_lock_gate_report(BASE_TASK, structured, max_revisions=5, legacy_result=reviewer_result)

        self.assertTrue(report.passed)
        self.assertTrue(all(check.passed for check in report.checks))

    def test_lock_gate_fails_on_critical_timeline_issue(self) -> None:
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "看似可锁，但仍有硬伤。",
            "major_issues": ["存在严重时间线矛盾，导致前后不一。"],
            "minor_issues": [],
            "information_gain": {"has_new_information": True, "new_information_items": ["发现了新线索。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "局面发生变化。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "主角做出新的动作偏移。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无重复。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }
        updated, report = apply_lock_gate(BASE_TASK, reviewer_result, max_revisions=5)

        self.assertFalse(report.passed)
        self.assertEqual(updated["verdict"], "rewrite")
        self.assertIn("锁定闸门未通过", updated["summary"])
        self.assertTrue(any(check.name == "timeline_blockers" and not check.passed for check in report.checks))

    def test_lock_gate_allows_manual_override_for_revision_policy(self) -> None:
        task_text = BASE_TASK + "\n# manual_lock_override\n人工确认允许超过自动修订上限后锁定\n"
        reviewer_result = {
            "task_id": "scene_012_draft_05-R6",
            "verdict": "lock",
            "summary": "人工复核后可锁定。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": True, "new_information_items": ["确认尸体来源地。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "本场局面向前推进。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "主角决定暂缓交差。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无重复。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }
        structured = build_structured_review_result(reviewer_result)
        report = build_lock_gate_report(task_text, structured, max_revisions=5, legacy_result=reviewer_result)

        self.assertTrue(report.passed)
        self.assertTrue(report.policy_override.present)
        self.assertIn("人工确认允许", report.policy_override.reason)

    def test_lock_gate_report_is_saved(self) -> None:
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "当前 scene 满足锁定条件。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": True, "new_information_items": ["确认了一个不可回退的新事实。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "剧情继续向前。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "主角决定夜里回查。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无重复。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }
        structured = build_structured_review_result(reviewer_result)
        report = build_lock_gate_report(BASE_TASK, structured, max_revisions=5, legacy_result=reviewer_result)

    def test_lock_gate_blocks_lock_without_information_gain(self) -> None:
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "氛围统一，可锁定。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": False, "new_information_items": []},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "局面略有变化。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "主角藏起了物件。"},
            "motif_redundancy": {"repeated_motifs": ["红绳"], "repetition_has_new_function": False, "redundancy_reason": "红绳只是在重复出现。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        updated, report = apply_lock_gate(BASE_TASK, reviewer_result, max_revisions=5)

        self.assertNotEqual(updated["verdict"], "lock")
        self.assertFalse(report.passed)
        self.assertTrue(any(check.name == "information_gain" and not check.passed for check in report.checks))

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            rel_path = save_lock_gate_report(root, report)
            data = json.loads((root / rel_path).read_text(encoding="utf-8"))
            self.assertEqual(rel_path, "03_locked/reports/scene_012_draft_05_lock_gate_report.json")
            self.assertEqual(data["task_id"], "scene_012_draft_05")
            self.assertIn("checks", data)
            self.assertTrue(any(check["name"] == "scene_purpose_defined" for check in data["checks"]))


if __name__ == "__main__":
    unittest.main()
