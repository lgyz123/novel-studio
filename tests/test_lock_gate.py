import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import app.lock_gate as lock_gate_module
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
    def test_lock_gate_matches_semantic_required_information_and_state_change(self) -> None:
        task_text = BASE_TASK + """
# required_information_gain
- 孟浮灯确认“阿绣”确实是平安符背面残存的字，不是自己一时看错。

# required_state_change
- 到场景结尾，孟浮灯对“阿绣”从偶然看到，变成决定先记住、先不说。
"""
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "当前 scene 满足锁定条件。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": True, "new_information_items": ["他借着风灯又看清平安符背面的字，确认那是阿绣，不是自己眼花。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "尸体被送到处理地点并完成了掩埋。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他把这个名字先记着，今夜不对任何人提起。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无重复。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = lock_gate_module.ROOT
            lock_gate_module.ROOT = root
            try:
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
                (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters/ch01_scene11.md").write_text("前文。", encoding="utf-8")
                (root / "03_locked/canon/ch01_state.md").write_text("阿绣目前只是被记住，还没有发展成调查念头。", encoding="utf-8")
                (root / "03_locked/state/story_state.json").write_text("{}", encoding="utf-8")
                (root / "02_working/drafts/ch01_scene12.md").write_text("他借着风灯又看清平安符背面的字，确认那是阿绣，不是自己眼花。这个名字今夜先到这里，他记住了，也只由他一个人先记着，到了那一步再说。", encoding="utf-8")

                structured = build_structured_review_result(reviewer_result)
                report = build_lock_gate_report(task_text, structured, max_revisions=5, legacy_result=reviewer_result)
            finally:
                lock_gate_module.ROOT = previous_root

        self.assertTrue(next(check for check in report.checks if check.name == "required_information_gain").passed)
        self.assertTrue(next(check for check in report.checks if check.name == "required_state_change").passed)

    def test_lock_gate_treats_story_blurb_requirement_as_generic_when_evidence_overlaps(self) -> None:
        task_text = BASE_TASK + """
# required_information_gain
- 保持与项目故事梗概一致：孟浮灯在运河与码头底层求活时，被一具来历异常的尸体和它牵出的名字卷入更大的秩序黑幕。
"""
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "当前 scene 满足锁定条件。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": True, "new_information_items": ["他从那具尸体腰间摸到刻着名字的旧牌，意识到自己已被卷进码头背后的黑幕。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "主角因此决定去找老船工核对来处。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他先把旧牌藏进袖口，再去找老船工。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无重复。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = lock_gate_module.ROOT
            lock_gate_module.ROOT = root
            try:
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
                (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters/ch01_scene11.md").write_text("前文。", encoding="utf-8")
                (root / "03_locked/canon/ch01_state.md").write_text("章节状态。", encoding="utf-8")
                (root / "03_locked/state/story_state.json").write_text("{}", encoding="utf-8")
                (root / "02_working/drafts/ch01_scene12.md").write_text("他从那具尸体腰间摸到刻着名字的旧牌，意识到自己已被卷进码头背后的黑幕，于是先把旧牌藏进袖口，再去找老船工。", encoding="utf-8")

                structured = build_structured_review_result(reviewer_result)
                report = build_lock_gate_report(task_text, structured, max_revisions=5, legacy_result=reviewer_result)
            finally:
                lock_gate_module.ROOT = previous_root

        self.assertTrue(next(check for check in report.checks if check.name == "required_information_gain").passed)

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
        with tempfile.TemporaryDirectory() as tmp_dir:
            previous_root = lock_gate_module.ROOT
            lock_gate_module.ROOT = Path(tmp_dir)
            try:
                structured = build_structured_review_result(reviewer_result)
                report = build_lock_gate_report(BASE_TASK, structured, max_revisions=5, legacy_result=reviewer_result)
            finally:
                lock_gate_module.ROOT = previous_root

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
        with tempfile.TemporaryDirectory() as tmp_dir:
            previous_root = lock_gate_module.ROOT
            lock_gate_module.ROOT = Path(tmp_dir)
            try:
                structured = build_structured_review_result(reviewer_result)
                report = build_lock_gate_report(task_text, structured, max_revisions=5, legacy_result=reviewer_result)
            finally:
                lock_gate_module.ROOT = previous_root

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

    def test_lock_gate_blocks_lock_without_state_transition_evidence(self) -> None:
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "气氛统一，可锁定。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": False, "new_information_items": []},
            "plot_progress": {"has_plot_progress": False, "progress_reason": ""},
            "character_decision": {"has_decision_or_behavior_shift": False, "decision_detail": ""},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无重复。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        updated, report = apply_lock_gate(BASE_TASK, reviewer_result, max_revisions=5)

        self.assertNotEqual(updated["verdict"], "lock")
        self.assertTrue(any(check.name == "state_transition_evidence" and not check.passed for check in report.checks))

    def test_lock_gate_blocks_disallowed_same_function_motif_reuse(self) -> None:
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "结构上可锁定。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": True, "new_information_items": ["看见红绳又一次只是晃动。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "气氛继续过渡。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他压下追问。"},
            "motif_redundancy": {
                "repeated_motifs": ["红绳"],
                "new_function_motifs": [],
                "stale_function_motifs": ["红绳"],
                "repeated_same_function_motifs": ["红绳"],
                "consecutive_same_function_motifs": ["红绳"],
                "repetition_has_new_function": False,
                "same_function_reuse_allowed": False,
                "redundancy_reason": "红绳在相邻场景连续承担同一过渡功能。",
            },
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        updated, report = apply_lock_gate(BASE_TASK, reviewer_result, max_revisions=5)

        self.assertNotEqual(updated["verdict"], "lock")
        self.assertTrue(any(check.name == "motif_redundancy" and not check.passed for check in report.checks))

    def test_lock_gate_blocks_lock_when_task_required_information_and_decision_do_not_land(self) -> None:
        task_text = BASE_TASK + """
# scene_function
发现线索

# required_information_gain
- 确认铜钱背面的血迹来源

# decision_requirement
主角必须把疑问转成一次明确动作，例如记下、收起或回看现场。

# required_state_change
- 主角认知变化
"""
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "氛围完整，可锁。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": False, "new_information_items": []},
            "plot_progress": {"has_plot_progress": False, "progress_reason": "只是继续感受潮气。"},
            "character_decision": {"has_decision_or_behavior_shift": False, "decision_detail": "他只是站着发怔。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无重复。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = lock_gate_module.ROOT
            lock_gate_module.ROOT = root
            try:
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
                (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters/ch01_scene11.md").write_text("孟浮灯刚收工，只记得袖里那枚铜钱硌得腕骨发凉。", encoding="utf-8")
                (root / "03_locked/canon/ch01_state.md").write_text("- 当前仍缺少新线索\n", encoding="utf-8")
                (root / "03_locked/state/story_state.json").write_text("{}", encoding="utf-8")
                (root / "02_working/drafts/ch01_scene12.md").write_text("潮气贴着棚屋往上爬，他望着水面，半晌没有动。", encoding="utf-8")

                updated, report = apply_lock_gate(task_text, reviewer_result, max_revisions=5)
            finally:
                lock_gate_module.ROOT = previous_root

        self.assertNotEqual(updated["verdict"], "lock")
        self.assertTrue(any(check.name == "required_information_gain" and not check.passed for check in report.checks))
        self.assertTrue(any(check.name == "decision_requirement" and not check.passed for check in report.checks))
        self.assertTrue(any(check.name == "required_state_change" and not check.passed for check in report.checks))
        self.assertTrue(any(check.name == "scene_function_landed" and not check.passed for check in report.checks))

    def test_lock_gate_blocks_lock_when_chapter_state_and_tracker_consistency_break(self) -> None:
        task_text = BASE_TASK + """
# scene_function
触发调查
"""
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "有轻推进。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": True, "new_information_items": ["他重新摸出了平安符。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "他准备追问这个名字。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他决定立刻去追问。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无重复。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = lock_gate_module.ROOT
            lock_gate_module.ROOT = root
            try:
                tracker_dir = root / "03_locked/state/trackers"
                tracker_dir.mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
                (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters/ch01_scene11.md").write_text("他把平安符塞进窝棚木板下。", encoding="utf-8")
                (root / "03_locked/canon/ch01_state.md").write_text("- 他尚未形成调查念头，也不该主动追问这条线索\n", encoding="utf-8")
                (root / "03_locked/state/story_state.json").write_text("{}", encoding="utf-8")
                (root / "02_working/drafts/ch01_scene12.md").write_text("他把平安符从怀里摸出来，立刻追问旁人这个名字的来处。", encoding="utf-8")
                (tracker_dir / "ch01_revelation_tracker.json").write_text('{"chapter_id": "ch01", "confirmed_facts": [], "suspected_facts": [], "unrevealed_facts": [], "forbidden_premature_reveals": []}', encoding="utf-8")
                (tracker_dir / "ch01_artifact_state.json").write_text('{"chapter_id": "ch01", "items": [{"item_id": "artifact_001", "label": "平安符", "holder": "待确认", "location": "窝棚木板下", "visibility": "hidden", "significance_level": "medium", "last_changed_scene": "ch01_scene11", "linked_facts": []}]}', encoding="utf-8")
                (tracker_dir / "ch01_chapter_progress.json").write_text('{"chapter_id": "ch01", "scene_summaries": []}', encoding="utf-8")
                (tracker_dir / "ch01_chapter_motif_tracker.json").write_text('{"chapter_id": "ch01", "active_motifs": []}', encoding="utf-8")

                updated, report = apply_lock_gate(task_text, reviewer_result, max_revisions=5)
            finally:
                lock_gate_module.ROOT = previous_root

        self.assertNotEqual(updated["verdict"], "lock")
        self.assertTrue(any(check.name == "chapter_state_alignment" and not check.passed for check in report.checks))

    def test_lock_gate_blocks_over_quota_transition_scene(self) -> None:
        task_text = BASE_TASK + """
# scene_function
过渡/氛围
"""
        reviewer_result = {
            "task_id": "scene_012_draft_05",
            "verdict": "lock",
            "summary": "承接自然。",
            "major_issues": [],
            "minor_issues": [],
            "information_gain": {"has_new_information": True, "new_information_items": ["他又闻到了同样的潮气。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "只是延续前场余波。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他暂时没有开口。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无重复。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = lock_gate_module.ROOT
            lock_gate_module.ROOT = root
            try:
                tracker_dir = root / "03_locked/state/trackers"
                tracker_dir.mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
                (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters/ch01_scene11.md").write_text("风从河面压过来，他只是看着水色发怔。", encoding="utf-8")
                (root / "03_locked/canon/ch01_state.md").write_text("- 需要尽快切离连续过渡场\n", encoding="utf-8")
                (root / "03_locked/state/story_state.json").write_text("{}", encoding="utf-8")
                (root / "02_working/drafts/ch01_scene12.md").write_text("潮气更重了，他站在原地，仍旧什么也没做。", encoding="utf-8")
                (tracker_dir / "ch01_revelation_tracker.json").write_text('{"chapter_id": "ch01"}', encoding="utf-8")
                (tracker_dir / "ch01_artifact_state.json").write_text('{"chapter_id": "ch01", "items": []}', encoding="utf-8")
                (tracker_dir / "ch01_chapter_motif_tracker.json").write_text('{"chapter_id": "ch01", "active_motifs": []}', encoding="utf-8")
                (tracker_dir / "ch01_chapter_progress.json").write_text(
                    json.dumps(
                        {
                            "chapter_id": "ch01",
                            "scene_summaries": [
                                {"scene_id": "ch01_scene10", "scene_function": "过渡/氛围"},
                                {"scene_id": "ch01_scene11", "scene_function": "过渡/氛围"},
                            ],
                            "consecutive_transition_scene_count": 2,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                updated, report = apply_lock_gate(task_text, reviewer_result, max_revisions=5)
            finally:
                lock_gate_module.ROOT = previous_root

        self.assertNotEqual(updated["verdict"], "lock")
        self.assertTrue(any(check.name == "weak_scene_quota" and not check.passed for check in report.checks))


if __name__ == "__main__":
    unittest.main()
