import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.analyze_scene_sequence import analyze_chapter, render_text_report


class AnalyzeSceneSequenceTest(unittest.TestCase):
    def test_analyze_chapter_reports_stagnation_repetition_and_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/reports").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state/trackers").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
            (root / "02_working/reviews").mkdir(parents=True, exist_ok=True)

            (root / "03_locked/chapters/ch01_scene01.md").write_text("孟浮灯看见半截铜钱，记下了它掉落的位置。", encoding="utf-8")
            (root / "03_locked/chapters/ch01_scene02.md").write_text("红绳在风里轻轻晃，他只是望着水面，没有开口。", encoding="utf-8")
            (root / "03_locked/chapters/ch01_scene03.md").write_text("红绳还在晃，他把平安符从怀里摸出来，想起阿绣像是旧识。", encoding="utf-8")

            (root / "03_locked/state/story_state.json").write_text("{}", encoding="utf-8")
            (root / "03_locked/state/trackers/ch01_chapter_motif_tracker.json").write_text(
                json.dumps(
                    {
                        "chapter_id": "ch01",
                        "active_motifs": [
                            {
                                "motif_id": "artifact_motif_hongsheng",
                                "category": "artifact_motif",
                                "label": "红绳",
                                "recent_usage_count": 3,
                                "recent_functions": ["过渡/氛围", "过渡/氛围", "过渡/氛围"],
                                "last_function": "过渡/氛围",
                                "function_novelty_score": 0.0,
                                "redundancy_risk": "high",
                                "only_if_new_function": True,
                                "allow_next_scene": False,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (root / "03_locked/state/trackers/ch01_revelation_tracker.json").write_text('{"chapter_id": "ch01"}', encoding="utf-8")
            (root / "03_locked/state/trackers/ch01_artifact_state.json").write_text('{"chapter_id": "ch01", "items": []}', encoding="utf-8")
            (root / "03_locked/state/trackers/ch01_chapter_progress.json").write_text(
                json.dumps(
                    {
                        "chapter_id": "ch01",
                        "scene_summaries": [
                            {"scene_id": "ch01_scene01", "scene_function": "发现线索"},
                            {"scene_id": "ch01_scene02", "scene_function": "过渡/氛围"},
                            {"scene_id": "ch01_scene03", "scene_function": "过渡/氛围"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            summaries = {
                "ch01_scene01": {
                    "scene_id": "ch01_scene01",
                    "scene_function": "发现线索",
                    "new_information_items": ["确认了半截铜钱的位置。"],
                    "protagonist_decision": "他记下了位置。",
                    "state_changes": ["protagonist_mode: 观察/求活 -> 留意线索"],
                    "motifs_used": ["半截铜钱"],
                    "motif_functions": {"半截铜钱": ["发现线索"]},
                    "artifacts_changed": [{"label": "半截铜钱"}],
                    "canon_risk_flags": [],
                },
                "ch01_scene02": {
                    "scene_id": "ch01_scene02",
                    "scene_function": "过渡/氛围",
                    "new_information_items": [],
                    "protagonist_decision": "",
                    "state_changes": [],
                    "motifs_used": ["红绳"],
                    "motif_functions": {"红绳": ["过渡/氛围"]},
                    "artifacts_changed": [],
                    "canon_risk_flags": [],
                },
                "ch01_scene03": {
                    "scene_id": "ch01_scene03",
                    "scene_function": "过渡/氛围",
                    "new_information_items": [],
                    "protagonist_decision": "",
                    "state_changes": [],
                    "motifs_used": ["红绳", "平安符"],
                    "motif_functions": {"红绳": ["过渡/氛围"], "平安符": ["过渡/氛围"]},
                    "artifacts_changed": [],
                    "canon_risk_flags": ["物件“平安符”当前所在位置应为“窝棚木板下”，但正文写法与现有 artifact_state 不一致。", "关系未知项“阿绣是谁”仍未确认，但正文已经写成熟识关系。"],
                },
            }
            for scene_id, summary in summaries.items():
                (root / f"03_locked/reports/{scene_id}_scene_summary.json").write_text(
                    json.dumps({"chapter_id": "ch01", "scene_id": scene_id, "scene_summary": summary, "chapter_structure_summary": {}}, ensure_ascii=False),
                    encoding="utf-8",
                )

            reviews = {
                "2026-04-07-001_ch01_scene01_auto_review_result.json": {
                    "verdict": "lock",
                    "information_gain": {"new_information_items": ["确认了半截铜钱的位置。"]},
                    "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他记下了位置。"},
                    "motif_redundancy": {"repeated_motifs": [], "repeated_same_function_motifs": []},
                    "canon_consistency": {"consistency_issues": []},
                },
                "2026-04-07-002_ch01_scene02_auto_review_result.json": {
                    "verdict": "revise",
                    "information_gain": {"new_information_items": []},
                    "character_decision": {"has_decision_or_behavior_shift": False, "decision_detail": ""},
                    "motif_redundancy": {"repeated_motifs": ["红绳"], "repeated_same_function_motifs": ["红绳"]},
                    "canon_consistency": {"consistency_issues": []},
                },
                "2026-04-07-003_ch01_scene03_auto_review_result.json": {
                    "verdict": "revise",
                    "information_gain": {"new_information_items": []},
                    "character_decision": {"has_decision_or_behavior_shift": False, "decision_detail": ""},
                    "motif_redundancy": {"repeated_motifs": ["红绳"], "repeated_same_function_motifs": ["红绳"]},
                    "canon_consistency": {"consistency_issues": ["物件“平安符”当前所在位置应为“窝棚木板下”，但正文写法与现有 artifact_state 不一致。", "关系未知项“阿绣是谁”仍未确认，但正文已经写成熟识关系。"]},
                },
            }
            for filename, payload in reviews.items():
                (root / "02_working/reviews" / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            lock_reports = {
                "2026-04-07-001_ch01_scene01_auto_lock_gate_report.json": {"passed": True, "checks": []},
                "2026-04-07-002_ch01_scene02_auto_lock_gate_report.json": {"passed": False, "checks": [{"name": "required_information_gain", "passed": False, "details": "missing"}]},
                "2026-04-07-003_ch01_scene03_auto_lock_gate_report.json": {"passed": False, "checks": [{"name": "chapter_state_alignment", "passed": False, "details": "物件“平安符”当前所在位置应为“窝棚木板下”，但正文写法与现有 artifact_state 不一致。；关系未知项“阿绣是谁”仍未确认，但正文已经写成熟识关系。"}]},
            }
            for filename, payload in lock_reports.items():
                (root / "03_locked/reports" / filename).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            report = analyze_chapter(root, "ch01")
            text_report = render_text_report(report)

        self.assertEqual(report["scene_count"], 3)
        self.assertEqual(report["scene_type_sequence"][0], "discovery")
        self.assertIn("ch01_scene02", report["stagnant_scenes"])
        self.assertIn("ch01_scene03", report["stagnant_scenes"])
        self.assertTrue(any(run["scene_ids"] == ["ch01_scene02", "ch01_scene03"] for run in report["same_function_runs"]))
        self.assertIn("ch01_scene03", report["artifact_drift_scenes"])
        self.assertIn("ch01_scene03", report["reveal_risk_scenes"])
        self.assertTrue(report["merge_candidates"])
        self.assertIn("ch01_scene03", report["rewrite_candidates"])
        self.assertIn("ch01_scene03", report["focus_review_scenes"])
        self.assertTrue(any(item["label"] == "红绳" and item["redundancy_risk"] == "high" for item in report["high_risk_motifs"]))
        self.assertIn("建议重写", text_report)
        self.assertIn("同功能连续段", text_report)


if __name__ == "__main__":
    unittest.main()