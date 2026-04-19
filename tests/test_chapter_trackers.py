import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.chapter_trackers import (
    detect_artifact_state_conflicts,
    detect_forbidden_reveal_violations,
    extract_candidate_motifs_from_text,
    load_tracker_bundle,
    update_trackers_on_lock,
)


class ChapterTrackersTest(unittest.TestCase):
    def test_extract_candidate_motifs_from_text_filters_polluted_phrase_fragments(self) -> None:
        text = "风带着水腥气钻进棚屋，轻则扣钱，可这块牌却还挂在码头边。孟浮灯想起老张头说过的话。"

        motifs = extract_candidate_motifs_from_text(text)
        labels = {label for _, label in motifs}

        self.assertIn("棚屋", labels)
        self.assertNotIn("风带着水腥气", labels)
        self.assertNotIn("轻则扣钱", labels)
        self.assertNotIn("可这块牌", labels)
        self.assertNotIn("想起老张头说过", labels)
        self.assertNotIn("一个", labels)
        self.assertNotIn("两个字", labels)
        self.assertNotIn("一块木牌", labels)

    def test_load_tracker_bundle_filters_polluted_motif_labels_from_existing_tracker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tracker_dir = root / "03_locked/state/trackers"
            tracker_dir.mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
            (tracker_dir / "ch01_chapter_motif_tracker.json").write_text(
                json.dumps(
                    {
                        "chapter_id": "ch01",
                        "active_motifs": [
                            {"motif_id": "environment_motif_码头", "category": "environment_motif", "label": "码头"},
                            {"motif_id": "environment_motif_轻则扣钱", "category": "environment_motif", "label": "轻则扣钱"},
                            {"motif_id": "smell_motif_混着水腥气", "category": "smell_motif", "label": "混着水腥气"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            bundle = load_tracker_bundle(root, "ch01", chapter_state_text="", story_state={}, upto_scene_id=None)

        labels = [item["label"] for item in bundle["chapter_motif_tracker"]["active_motifs"]]
        self.assertIn("码头", labels)
        self.assertNotIn("轻则扣钱", labels)
        self.assertNotIn("混着水腥气", labels)

    def test_detect_artifact_state_conflicts_ignores_unresolved_status_location(self) -> None:
        conflicts = detect_artifact_state_conflicts(
            "孟浮灯把红绳和平安符先裹进油布，贴身收着，暂不声张。",
            {
                "items": [
                    {"label": "红绳", "holder": "待确认", "location": "状态待确认", "visibility": "unknown"},
                    {"label": "平安符", "holder": "待确认", "location": "状态待确认", "visibility": "unknown"},
                ]
            },
        )

        self.assertEqual(conflicts, [])

    def test_detect_artifact_state_conflicts_accepts_protagonist_alias_and_semantic_carry_location(self) -> None:
        conflicts = detect_artifact_state_conflicts(
            "孟浮灯把红绳和平安符分开包好，塞进最内侧的里襟，贴着胸口压平。",
            {
                "items": [
                    {"label": "红绳和平安符", "holder": "主角", "location": "贴身保留", "visibility": "hidden"},
                    {"label": "麻绳", "holder": "主角", "location": "随身携带", "visibility": "hidden"},
                    {"label": "绳", "holder": "旧坑边沿", "location": "状态待确认", "visibility": "unknown"},
                ]
            },
        )

        self.assertEqual(conflicts, [])

    def test_detect_artifact_state_conflicts_allows_private_inspection_of_hidden_item(self) -> None:
        conflicts = detect_artifact_state_conflicts(
            "孟浮灯把那截红绳放到桌上，在灯下看了一会儿，又重新包回油布里，塞进怀里。",
            {
                "items": [
                    {"label": "那截红绳", "holder": "主角", "location": "随身携带", "visibility": "hidden"},
                ]
            },
        )

        self.assertEqual(conflicts, [])

    def test_load_tracker_bundle_filters_polluted_artifact_labels_and_holders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tracker_dir = root / "03_locked/state/trackers"
            tracker_dir.mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
            (tracker_dir / "ch01_artifact_state.json").write_text(
                json.dumps(
                    {
                        "chapter_id": "ch01",
                        "items": [
                            {"item_id": "artifact_平安符", "label": "平安符", "holder": "主角", "location": "随身携带"},
                            {"item_id": "artifact_不是绳", "label": "不是绳", "holder": "觉到几处", "location": "待确认"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            bundle = load_tracker_bundle(root, "ch01", chapter_state_text="", story_state={}, upto_scene_id=None)

        labels = [item["label"] for item in bundle["artifact_state"]["items"]]
        self.assertIn("平安符", labels)
        self.assertNotIn("不是绳", labels)

    def test_load_tracker_bundle_filters_action_phrase_artifact_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tracker_dir = root / "03_locked/state/trackers"
            tracker_dir.mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
            (tracker_dir / "ch01_artifact_state.json").write_text(
                json.dumps(
                    {
                        "chapter_id": "ch01",
                        "items": [
                            {"item_id": "artifact_麻绳", "label": "麻绳", "holder": "主角", "location": "随身携带"},
                            {"item_id": "artifact_松开麻绳", "label": "松开麻绳", "holder": "他蹲", "location": "待确认"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            bundle = load_tracker_bundle(root, "ch01", chapter_state_text="", story_state={}, upto_scene_id=None)

        labels = [item["label"] for item in bundle["artifact_state"]["items"]]
        holders = {item["label"]: item["holder"] for item in bundle["artifact_state"]["items"]}
        self.assertIn("麻绳", labels)
        self.assertNotIn("松开麻绳", labels)
        self.assertEqual(holders["麻绳"], "主角")

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

        motif_tracker = bundle["chapter_motif_tracker"]
        motif_entry = next(item for item in motif_tracker["active_motifs"] if item["label"] == "平安符")
        self.assertEqual(motif_entry["recent_functions"][-1], "发现线索")
        self.assertEqual(motif_entry["last_function"], "发现线索")
        self.assertGreaterEqual(motif_entry["function_novelty_score"], 1.0)
        self.assertEqual(motif_entry["redundancy_risk"], "low")

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

    def test_update_trackers_on_lock_marks_same_function_motif_reuse_risk(self) -> None:
        task_text = """# task_id
2026-04-07-012_ch01_scene03_auto

# goal
继续推进。

# scene_function
过渡/氛围

# chapter_state
03_locked/canon/ch01_state.md
"""
        reviewer_result = {
            "information_gain": {"has_new_information": False, "new_information_items": []},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "保持场景过渡。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他暂时压下念头。"},
            "motif_redundancy": {
                "repeated_motifs": ["红绳"],
                "new_function_motifs": [],
                "stale_function_motifs": ["红绳"],
                "repeated_same_function_motifs": ["红绳"],
                "consecutive_same_function_motifs": ["红绳"],
                "repetition_has_new_function": False,
                "same_function_reuse_allowed": False,
                "redundancy_reason": "红绳连续承担同一过渡功能，没有新的叙事作用。",
            },
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tracker_dir = root / "03_locked/state/trackers"
            tracker_dir.mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon/ch01_state.md").write_text("# ch01 当前状态\n", encoding="utf-8")
            (root / "03_locked/chapters/ch01_scene03.md").write_text("红绳贴着腕骨轻轻晃，他只是站着发怔。", encoding="utf-8")
            (tracker_dir / "ch01_chapter_motif_tracker.json").write_text(
                json.dumps(
                    {
                        "chapter_id": "ch01",
                        "active_motifs": [
                            {
                                "motif_id": "artifact_motif_hongsheng",
                                "category": "artifact_motif",
                                "label": "红绳",
                                "narrative_functions": ["过渡/氛围"],
                                "recent_scene_ids": ["ch01_scene01", "ch01_scene02"],
                                "recent_usage_count": 2,
                                "recent_functions": ["过渡/氛围", "过渡/氛围"],
                                "last_function": "过渡/氛围",
                                "function_novelty_score": 0.0,
                                "allow_next_scene": False,
                                "only_if_new_function": True,
                                "redundancy_risk": "high",
                                "notes": "repeated",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (tracker_dir / "ch01_revelation_tracker.json").write_text('{"chapter_id": "ch01"}', encoding="utf-8")
            (tracker_dir / "ch01_artifact_state.json").write_text('{"chapter_id": "ch01", "items": []}', encoding="utf-8")
            (tracker_dir / "ch01_chapter_progress.json").write_text('{"chapter_id": "ch01"}', encoding="utf-8")

            update_trackers_on_lock(root, task_text, "03_locked/chapters/ch01_scene03.md", reviewer_result)
            bundle = load_tracker_bundle(root, "ch01", chapter_state_text="# ch01 当前状态\n", story_state={}, upto_scene_id="ch01_scene03")

        motif_entry = next(item for item in bundle["chapter_motif_tracker"]["active_motifs"] if item["label"] == "红绳")
        self.assertEqual(motif_entry["recent_functions"][-1], "过渡/氛围")
        self.assertEqual(motif_entry["last_function"], "过渡/氛围")
        self.assertEqual(motif_entry["function_novelty_score"], 0.0)
        self.assertEqual(motif_entry["redundancy_risk"], "high")
        self.assertFalse(motif_entry["allow_next_scene"])
        self.assertTrue(motif_entry["only_if_new_function"])


if __name__ == "__main__":
    unittest.main()
