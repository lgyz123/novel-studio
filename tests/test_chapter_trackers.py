import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.chapter_trackers import detect_forbidden_reveal_violations, load_tracker_bundle, update_trackers_on_lock


class ChapterTrackersTest(unittest.TestCase):
    def test_update_trackers_on_lock_writes_expanded_revelation_artifact_and_chapter_state(self) -> None:
        task_text = """# task_id
2026-04-07-010_ch01_scene02_auto

# goal
承接上一场，继续推进本章。

# chapter_state
03_locked/canon/ch01_state.md
"""
        chapter_state_text = """# ch01 当前状态

## 暂不展开的内容
- 不提前揭示阿绣真实身份

## 已锁定线索
- 平安符背面写着名字

## 当前主角状态
- 主角尚未形成明确调查行动
- 他无法把这个名字轻易放下
"""
        locked_text = "孟浮灯看见平安符背面写着阿绣，像是旧识留下的东西，却还是把平安符塞回袖里，没有立刻去问。"
        reviewer_result = {
            "information_gain": {"has_new_information": True, "new_information_items": ["确认平安符背面写着‘阿绣’。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "关键物件状态与认知压力发生变化。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他把平安符塞回袖里，没有立刻追问。"},
            "motif_redundancy": {"repeated_motifs": ["平安符"], "repetition_has_new_function": True, "redundancy_reason": "承担了新信息功能。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon/ch01_state.md").write_text(chapter_state_text, encoding="utf-8")
            (root / "03_locked/chapters/ch01_scene02.md").write_text(locked_text, encoding="utf-8")
            (root / "03_locked/state/story_state.json").write_text(
                json.dumps(
                    {
                        "characters": {
                            "protagonist": {
                                "known_facts": ["平安符存在异常"],
                                "open_tensions": ["阿绣是谁"],
                                "active_goals": ["维持码头日常"],
                            }
                        },
                        "unresolved_promises": [{"description": "不提前揭示阿绣真实身份"}],
                        "items": [{"id": "ITEM-001", "name": "平安符", "owner": "主角", "status": "窝棚木板下", "last_seen_in": "ch01_scene01"}],
                        "relationship_deltas": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            outputs = update_trackers_on_lock(root, task_text, "03_locked/chapters/ch01_scene02.md", reviewer_result)
            bundle = load_tracker_bundle(root, "ch01", chapter_state_text=chapter_state_text, story_state=json.loads((root / "03_locked/state/story_state.json").read_text(encoding="utf-8")), upto_scene_id="ch01_scene02")
            report = json.loads((root / outputs["scene_summary_report_file"]).read_text(encoding="utf-8"))

        self.assertIn("revelation_tracker_file", outputs)
        self.assertIn("artifact_state_file", outputs)
        self.assertIn("chapter_progress_file", outputs)
        self.assertIn("scene_summary_report_file", outputs)

        revelation = bundle["revelation_tracker"]
        self.assertIn("protagonist_known_facts", revelation)
        self.assertIn("reader_known_facts", revelation)
        self.assertIn("relationship_unknowns", revelation)
        self.assertTrue(any("阿绣" in item for item in revelation["confirmed_facts"]))
        self.assertTrue(any("旧识" in item or "像是" in item for item in revelation["suspected_facts"]))
        self.assertTrue(revelation["forbidden_premature_reveals"])

        artifact_state = bundle["artifact_state"]
        artifact = next(item for item in artifact_state["items"] if item["label"] == "平安符")
        self.assertEqual(artifact["holder"], "主角")
        self.assertEqual(artifact["location"], "随身携带")
        self.assertEqual(artifact["visibility"], "hidden")
        self.assertTrue(artifact["linked_facts"])

        chapter_progress = bundle["chapter_progress"]
        self.assertIn("protagonist_goal", chapter_progress)
        self.assertIn("protagonist_mode", chapter_progress)
        self.assertIn("investigation_stage", chapter_progress)
        self.assertIn("risk_level", chapter_progress)
        self.assertIn("current_relationships", chapter_progress)
        self.assertIn("unresolved_questions", chapter_progress)
        self.assertTrue(any(item.startswith("ch01_scene02:") for item in chapter_progress["completed_scene_functions"]))
        self.assertTrue(chapter_progress["scene_summaries"])
        scene_summary = chapter_progress["scene_summaries"][-1]
        self.assertEqual(scene_summary["scene_id"], "ch01_scene02")
        self.assertEqual(scene_summary["scene_function"], "发现线索")
        self.assertTrue(scene_summary["motifs_used"])
        self.assertTrue(scene_summary["artifacts_changed"])
        self.assertIn("chapter_structure_summary", chapter_progress)
        self.assertEqual(chapter_progress["chapter_structure_summary"]["first_clue_scene_id"], "ch01_scene02")

        self.assertEqual(report["scene_summary"]["scene_id"], "ch01_scene02")
        self.assertEqual(report["chapter_structure_summary"]["first_artifact_change_scene_id"], "ch01_scene02")

    def test_update_trackers_on_lock_tracks_consecutive_transition_runs_in_structure_summary(self) -> None:
        task_text = """# task_id
2026-04-07-011_ch01_scene03_auto

# goal
继续推进。

# chapter_state
03_locked/canon/ch01_state.md
"""
        chapter_state_text = """# ch01 当前状态

## 暂不展开的内容
- 暂不解释河道尽头的旧事
"""
        scene02_text = "他在潮气里收紧衣领，闻见棚屋边的腥味，半晌没有说话。"
        scene03_text = "风从棚屋缝里灌进来，他盯着水面发怔，那点寒意一直堵在喉头。"
        reviewer_result = {
            "information_gain": {"has_new_information": False, "new_information_items": []},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "情绪与局面继续过渡。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他压下追问念头，继续做活。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": ""},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon/ch01_state.md").write_text(chapter_state_text, encoding="utf-8")
            (root / "03_locked/chapters/ch01_scene02.md").write_text(scene02_text, encoding="utf-8")
            (root / "03_locked/chapters/ch01_scene03.md").write_text(scene03_text, encoding="utf-8")
            (root / "03_locked/state/story_state.json").write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")

            update_trackers_on_lock(root, task_text, "03_locked/chapters/ch01_scene02.md", reviewer_result)
            outputs = update_trackers_on_lock(root, task_text, "03_locked/chapters/ch01_scene03.md", reviewer_result)

            bundle = load_tracker_bundle(root, "ch01", chapter_state_text=chapter_state_text, story_state={}, upto_scene_id="ch01_scene03")
            report = json.loads((root / outputs["scene_summary_report_file"]).read_text(encoding="utf-8"))

        chapter_structure_summary = bundle["chapter_progress"]["chapter_structure_summary"]
        self.assertTrue(chapter_structure_summary["consecutive_transition_runs"])
        run = chapter_structure_summary["consecutive_transition_runs"][-1]
        self.assertEqual(run["start_scene_id"], "ch01_scene02")
        self.assertEqual(run["end_scene_id"], "ch01_scene03")
        self.assertEqual(run["length"], 2)
        self.assertEqual(report["chapter_structure_summary"]["consecutive_transition_runs"][-1]["length"], 2)

    def test_detect_forbidden_reveal_violations_reads_forbidden_and_relationship_unknowns(self) -> None:
        tracker = {
            "forbidden_premature_reveals": ["阿绣真实身份"],
            "relationship_unknowns": ["阿绣是谁"],
        }
        draft_text = "他忽然想起阿绣总会替他把领口压平，像是早就与她相识。"

        violations = detect_forbidden_reveal_violations(draft_text, tracker)

        self.assertTrue(violations)
        self.assertTrue(any("阿绣" in item for item in violations))


if __name__ == "__main__":
    unittest.main()
