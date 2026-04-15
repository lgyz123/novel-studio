import tempfile
import json
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import app.review_scene as review_scene_module


class ReviewSceneSanitizationTest(unittest.TestCase):
    def test_build_review_prompt_marks_based_on_as_reference_only(self) -> None:
        prompt = review_scene_module.build_review_prompt(
            None,
            task_text="# task_id\nscene11\n",
            chapter_state="chapter state",
            based_on_text="【scene10】前文内容",
            draft_text="【scene11】当前草稿",
        )

        self.assertIn("你审查的对象只有“待审草稿”一节", prompt)
        self.assertIn("不要把“直接前文 / 基准文本”误判为待审草稿", prompt)
        self.assertIn("information_gain", prompt)
        self.assertIn("plot_progress", prompt)
        self.assertIn("character_decision", prompt)
        self.assertIn("motif_redundancy", prompt)
        self.assertIn("canon_consistency", prompt)
        self.assertIn("前文内容", prompt)
        self.assertIn("当前草稿", prompt)
        self.assertNotIn("【scene10】", prompt)
        self.assertNotIn("【scene11】", prompt)

    def test_build_review_prompt_includes_dynamic_tracker_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = review_scene_module.ROOT
            review_scene_module.ROOT = root
            try:
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon/ch01_state.md").write_text("# ch01 当前状态\n\n## 暂不展开的内容\n- 不提前揭示阿绣替他收过尸账\n", encoding="utf-8")
                (root / "03_locked/chapters/ch01_scene01.md").write_text("孟浮灯摸到红绳，袖里还留着铁锈味。", encoding="utf-8")
                (root / "03_locked/state/story_state.json").write_text(
                    '{"characters": {"protagonist": {"known_facts": ["摸到红绳"]}}}',
                    encoding="utf-8",
                )

                prompt = review_scene_module.build_review_prompt(
                    None,
                    task_text="# task_id\n2026-04-03-017_ch01_scene02_auto\n\n# chapter_state\n03_locked/canon/ch01_state.md\n",
                    chapter_state="# ch01 当前状态\n\n## 暂不展开的内容\n- 不提前揭示阿绣替他收过尸账\n",
                    based_on_text="【scene01】孟浮灯摸到红绳。",
                    draft_text="【scene02】孟浮灯又看见红绳。",
                )
            finally:
                review_scene_module.ROOT = previous_root

        self.assertIn("【动态章节 tracker】", prompt)
        self.assertIn("chapter_motif_tracker", prompt)
        self.assertIn("revelation_tracker", prompt)

    def test_build_structural_review_signals_uses_dynamic_tracker_for_motif_and_artifact_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = review_scene_module.ROOT
            review_scene_module.ROOT = root
            try:
                tracker_dir = root / "03_locked/state/trackers"
                tracker_dir.mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon/ch01_state.md").write_text("章节状态", encoding="utf-8")
                (tracker_dir / "ch01_chapter_motif_tracker.json").write_text(
                    '{"chapter_id": "ch01", "active_motifs": [{"motif_id": "artifact_motif_hongsheng", "category": "artifact_motif", "label": "红绳", "narrative_functions": ["过渡/氛围"], "status": "active", "recent_scene_ids": ["ch01_scene01"], "recent_usage_count": 2, "allow_next_scene": false, "only_if_new_function": true, "notes": "repeated"}]}',
                    encoding="utf-8",
                )
                (tracker_dir / "ch01_revelation_tracker.json").write_text(
                    '{"chapter_id": "ch01", "confirmed_facts": [], "suspected_facts": [], "unrevealed_facts": [], "forbidden_premature_reveals": ["阿绣替他"]}',
                    encoding="utf-8",
                )
                (tracker_dir / "ch01_artifact_state.json").write_text(
                    '{"chapter_id": "ch01", "items": [{"item_id": "artifact_001", "label": "平安符", "holder": "待确认", "location": "窝棚木板下", "significance_level": "medium", "last_changed_scene": "ch01_scene01"}]}',
                    encoding="utf-8",
                )
                (tracker_dir / "ch01_chapter_progress.json").write_text(
                    '{"chapter_id": "ch01", "chapter_goal": "推进", "completed_scene_functions": [], "remaining_scene_functions": ["发现线索"], "consecutive_transition_scene_count": 1}',
                    encoding="utf-8",
                )

                signals = review_scene_module.build_structural_review_signals(
                    task_text="# task_id\n2026-04-03-017_ch01_scene02_auto\n\n# chapter_state\n03_locked/canon/ch01_state.md\n",
                    draft_text="红绳还在晃。红绳贴着腕骨，他只是发怔。后来他把平安符从怀里摸出来，还想起阿绣替他把领口压平。",
                    based_on_text="孟浮灯看见红绳，什么也没做。",
                    chapter_state="章节状态",
                )
            finally:
                review_scene_module.ROOT = previous_root

        self.assertIn("红绳", signals["motif_redundancy"]["repeated_motifs"])
        self.assertFalse(signals["motif_redundancy"]["repetition_has_new_function"])
        self.assertIn("红绳", signals["motif_redundancy"]["repeated_same_function_motifs"])
        self.assertIn("红绳", signals["motif_redundancy"]["consecutive_same_function_motifs"])
        self.assertFalse(signals["motif_redundancy"]["same_function_reuse_allowed"])
        self.assertFalse(signals["canon_consistency"]["is_consistent"])
        self.assertTrue(any("artifact_state" in item or "物件“平安符”" in item for item in signals["canon_consistency"]["consistency_issues"]))

    def test_sanitize_reviewer_raw_output_compresses_repeated_english_analysis(self) -> None:
        raw_text = " ".join(
            [
                "We need to review the draft.",
                "The assistant must output a single JSON object.",
                "The draft must not repeat the earlier content.",
            ]
            * 12
        )

        sanitized, meta = review_scene_module.sanitize_reviewer_raw_output(raw_text)

        self.assertTrue(meta["low_value_english"])
        self.assertGreater(meta["repeated_fragments"], 0)
        self.assertLess(len(sanitized), len(raw_text))
        self.assertIn("重复片段已压缩", sanitized)

    def test_build_local_review_fallback_downweights_low_confidence_english(self) -> None:
        result = review_scene_module.build_local_review_fallback(
            "scene_100",
            "We need to evaluate the draft. The assistant must output a single JSON object.",
            task_text="# constraints\n- 不急于解释‘阿绣’是谁\n",
            draft_text="孟浮灯只是想起阿绣，闻到铁锈味，喉头发紧。",
            based_on_text="孟浮灯想起阿绣，闻到铁锈味。",
            low_confidence=True,
        )

        self.assertEqual(result["verdict"], "revise")
        self.assertTrue(result["major_issues"])
        self.assertIn("无效英文分析", result["minor_issues"][0])
        self.assertIn("information_gain", result)
        self.assertFalse(result["information_gain"]["has_new_information"])
        self.assertFalse(result["plot_progress"]["has_plot_progress"])
        self.assertFalse(result["character_decision"]["has_decision_or_behavior_shift"])

    def test_structural_signals_recognize_throwing_object_as_decision_and_progress(self) -> None:
        signals = review_scene_module.build_structural_review_signals(
            task_text="# task_id\nscene_throw\n",
            draft_text="孟浮灯听见官船逼近，突然将铜铃往水里一扔，转身贴着芦苇根后退半步。",
            based_on_text="孟浮灯原本蹲在岸边。",
            chapter_state="当前仍处于求活观察阶段。",
        )

        self.assertTrue(signals["character_decision"]["has_decision_or_behavior_shift"])
        self.assertTrue(signals["plot_progress"]["has_plot_progress"])

    def test_local_reviewer_skips_json_refinement_for_meta_english(self) -> None:
        sanitized, meta = review_scene_module.sanitize_reviewer_raw_output(
            "We need to produce a JSON object. The assistant must output a single JSON object."
        )

        self.assertTrue(
            review_scene_module.should_skip_json_refinement_for_local_reviewer(
                {
                    "reviewer": {
                        "provider": "ollama",
                        "model": "gpt-oss:20b",
                        "base_url": "http://example.com",
                    }
                },
                sanitized,
                meta,
            )
        )

    def test_build_review_prompt_uses_compact_variant_for_local_reviewer(self) -> None:
        prompt = review_scene_module.build_review_prompt(
            {"reviewer": {"provider": "ollama"}},
            task_text="# task_id\nscene11\n",
            chapter_state="chapter state",
            based_on_text="前文",
            draft_text="当前草稿",
        )

        self.assertIn("你是小说 scene 审稿器", prompt)
        self.assertIn("只输出一个 JSON 对象", prompt)
        self.assertNotIn("你不是文风评论员", prompt)

    def test_local_reviewer_strategy_defaults_to_deterministic_primary(self) -> None:
        self.assertEqual(
            review_scene_module.get_local_reviewer_strategy({"reviewer": {"provider": "ollama"}}),
            "deterministic_primary",
        )

    def test_build_reviewer_trace_marks_deterministic_fallback(self) -> None:
        trace = review_scene_module.build_reviewer_trace(
            provider="ollama",
            mode="deterministic_fallback",
            json_refinement_attempted=False,
            deterministic_fallback_used=True,
            low_confidence=True,
            repeated_fragments=3,
        )

        self.assertEqual(trace["provider"], "ollama")
        self.assertEqual(trace["mode"], "deterministic_fallback")
        self.assertTrue(trace["deterministic_fallback_used"])
        self.assertTrue(trace["low_confidence"])
        self.assertEqual(trace["repeated_fragments"], 3)

    def test_normalize_review_result_dedupes_repeated_issue_text(self) -> None:
        result = {
            "task_id": "scene_101",
            "verdict": "rewrite",
            "task_goal_fulfilled": False,
            "major_issues": [
                "The draft must not repeat the earlier content.",
                "关键动作完成度不足。关键动作完成度不足。关键动作完成度不足。",
                "关键动作完成度不足。关键动作完成度不足。关键动作完成度不足。",
            ],
            "minor_issues": [],
            "recommended_next_step": "rewrite_scene",
            "summary": "We need to review the draft and output JSON.",
            "information_gain": {"has_new_information": True, "new_information_items": ["新发现了半截铜钱。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "主角因此改变了交差顺序。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他先把铜钱藏进袖口。"},
            "motif_redundancy": {"repeated_motifs": ["阿绣"], "repetition_has_new_function": True, "redundancy_reason": "母题复现触发了新动作。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        normalized = review_scene_module.normalize_review_result(
            result,
            "We need to review the draft. The assistant must output a single JSON object.",
            task_text="# constraints\n- 保持单视角\n",
            low_confidence=True,
            draft_text="孟浮灯把铜钱藏进袖口，决定先不交差。",
            based_on_text="孟浮灯刚刚收工。",
        )

        self.assertEqual(normalized["verdict"], "revise")
        self.assertGreaterEqual(len(normalized["major_issues"]), 1)
        self.assertTrue(any("关键动作完成度不足" in item for item in normalized["major_issues"]))
        self.assertTrue(any("无效英文分析" in item for item in normalized["minor_issues"]))
        self.assertFalse(any("The draft must" in item for item in normalized["major_issues"]))
        self.assertIn("information_gain", normalized)

    def test_normalize_review_result_fills_missing_recommended_next_step(self) -> None:
        result = {
            "verdict": "revise",
            "task_goal_fulfilled": False,
            "major_issues": ["关键动作完成度不足。"],
            "minor_issues": [],
            "summary": "当前 scene 方向正确，但动作牵引与场景闭环仍不够完整，更适合先小修。",
        }

        normalized = review_scene_module.normalize_review_result(
            result,
            "We need to evaluate the draft.",
            task_text="# constraints\n- 保持单视角\n",
            low_confidence=False,
            draft_text="孟浮灯把铜钱塞回衣内，决定等夜里再看。",
            based_on_text="孟浮灯刚收工回屋。",
        )

        self.assertEqual(normalized["verdict"], "revise")
        self.assertEqual(normalized["recommended_next_step"], "create_revision_task")

    def test_ensure_non_empty_structural_fields_fills_empty_decision_detail(self) -> None:
        payload = {
            "summary": "需要继续修订。",
            "character_decision": {
                "has_decision_or_behavior_shift": False,
                "decision_detail": "",
            },
            "plot_progress": {
                "has_plot_progress": False,
                "progress_reason": "",
            },
            "motif_redundancy": {
                "repeated_motifs": [],
                "new_function_motifs": [],
                "stale_function_motifs": [],
                "repeated_same_function_motifs": [],
                "consecutive_same_function_motifs": [],
                "repetition_has_new_function": True,
                "same_function_reuse_allowed": True,
                "redundancy_reason": "",
            },
        }

        normalized = review_scene_module.ensure_non_empty_structural_fields(payload)

        self.assertTrue(normalized["character_decision"]["decision_detail"])
        self.assertTrue(normalized["plot_progress"]["progress_reason"])

    def test_normalize_review_result_never_returns_empty_structural_strings(self) -> None:
        result = {
            "task_id": "scene_107",
            "verdict": "revise",
            "task_goal_fulfilled": False,
            "major_issues": ["推进不足。"],
            "minor_issues": [],
            "recommended_next_step": "create_revision_task",
            "summary": "需要修订。",
            "information_gain": {"has_new_information": False, "new_information_items": []},
            "plot_progress": {"has_plot_progress": False, "progress_reason": ""},
            "character_decision": {"has_decision_or_behavior_shift": False, "decision_detail": ""},
            "motif_redundancy": {
                "repeated_motifs": [],
                "new_function_motifs": [],
                "stale_function_motifs": [],
                "repeated_same_function_motifs": [],
                "consecutive_same_function_motifs": [],
                "repetition_has_new_function": True,
                "same_function_reuse_allowed": True,
                "redundancy_reason": "",
            },
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        normalized = review_scene_module.normalize_review_result(
            result,
            raw_review_text="Reviewer output was malformed.",
            task_text="# constraints\n- 保持单视角\n",
            low_confidence=False,
            draft_text="孟浮灯站在原地发怔。",
            based_on_text="孟浮灯刚收工。",
            chapter_state="阿绣这个名字已经留在他心里，但目前仍只是被记住。",
        )

        self.assertTrue(normalized["character_decision"]["decision_detail"])
        self.assertTrue(normalized["plot_progress"]["progress_reason"])
        self.assertTrue(normalized["motif_redundancy"]["redundancy_reason"])
        self.assertTrue(normalized["motif_redundancy"]["redundancy_reason"])

    def test_normalize_review_result_replaces_english_structural_fields_with_local_chinese(self) -> None:
        result = {
            "task_id": "scene_107b",
            "verdict": "revise",
            "task_goal_fulfilled": False,
            "major_issues": ["推进不足。"],
            "minor_issues": [],
            "recommended_next_step": "create_revision_task",
            "summary": "需要修订。",
            "information_gain": {"has_new_information": True, "new_information_items": ["Found a hidden receipt."]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "The plot moves forward."},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "He decides to hide it first."},
            "motif_redundancy": {
                "repeated_motifs": ["rope tail"],
                "new_function_motifs": [],
                "stale_function_motifs": [],
                "repeated_same_function_motifs": [],
                "consecutive_same_function_motifs": [],
                "repetition_has_new_function": True,
                "same_function_reuse_allowed": True,
                "redundancy_reason": "The repeated motif has a new function.",
            },
            "canon_consistency": {"is_consistent": True, "consistency_issues": ["No canon issue detected."]},
        }

        normalized = review_scene_module.normalize_review_result(
            result,
            raw_review_text="Need revision.",
            task_text="# constraints\n- 保持单视角\n",
            low_confidence=False,
            draft_text="孟浮灯把旧票塞进袖里，没有立刻上交，转身先回屋把门闩上。",
            based_on_text="孟浮灯刚收工回屋。",
            chapter_state="当前仍处于低烈度观察推进阶段。",
        )

        self.assertFalse(any("Found a hidden receipt" in item for item in normalized["information_gain"]["new_information_items"]))
        self.assertFalse(any("rope tail" in item for item in normalized["motif_redundancy"]["repeated_motifs"]))
        self.assertFalse("The plot moves forward." == normalized["plot_progress"]["progress_reason"])
        self.assertFalse("He decides to hide it first." == normalized["character_decision"]["decision_detail"])

    def test_normalize_review_result_drops_unexpected_fields(self) -> None:
        result = {
            "task_id": "scene_102",
            "verdict": "revise",
            "task_goal_fulfilled": False,
            "major_issues": ["核心推进不足。"],
            "minor_issues": [],
            "recommended_next_step": "create_revision_task",
            "summary": "需要继续修订。",
            "error": "章节状态未提供",
        }

        normalized = review_scene_module.normalize_review_result(
            result,
            "We need to evaluate the draft.",
            task_text="# constraints\n- 保持单视角\n",
            low_confidence=False,
            draft_text="孟浮灯闻到腐臭，想起阿绣，什么也没做。",
            based_on_text="孟浮灯闻到腐臭，想起阿绣。",
        )

        self.assertNotIn("error", normalized)
        self.assertEqual(normalized["task_id"], "scene_102")
        self.assertIn("information_gain", normalized)

    def test_normalize_review_result_blocks_lock_without_structural_progress(self) -> None:
        result = {
            "task_id": "scene_103",
            "verdict": "lock",
            "task_goal_fulfilled": True,
            "major_issues": [],
            "minor_issues": [],
            "recommended_next_step": "lock_scene",
            "summary": "氛围统一，可直接锁定。",
            "information_gain": {"has_new_information": False, "new_information_items": []},
            "plot_progress": {"has_plot_progress": False, "progress_reason": "没有推进。"},
            "character_decision": {"has_decision_or_behavior_shift": False, "decision_detail": "主角没有动作偏移。"},
            "motif_redundancy": {"repeated_motifs": ["阿绣", "红绳"], "repetition_has_new_function": False, "redundancy_reason": "母题复读。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        normalized = review_scene_module.normalize_review_result(
            result,
            "The draft atmosphere is strong.",
            task_text="# constraints\n- 不急于解释‘阿绣’是谁\n",
            draft_text="孟浮灯闻到铁锈味，想起阿绣，喉头发紧。",
            based_on_text="孟浮灯闻到铁锈味，想起阿绣。",
        )

        self.assertNotEqual(normalized["verdict"], "lock")
        self.assertTrue(normalized["major_issues"])

    def test_evaluate_scene_gate_marks_missing_information_items_as_high_risk(self) -> None:
        report = review_scene_module.evaluate_scene_gate(
            task_text="# constraints\n- 保持单视角\n",
            draft_text="孟浮灯闻到腐臭，想起阿绣，喉头发紧。",
            based_on_text="孟浮灯闻到腐臭，想起阿绣。",
            chapter_state="阿绣这个名字已经留在他心里，但目前仍只是被记住、被反复想起。",
            reviewer_result={
                "information_gain": {"has_new_information": True, "new_information_items": []},
                "character_decision": {"has_decision_or_behavior_shift": False, "decision_detail": ""},
            },
        )

        self.assertIn("reviewer_missing_information_items", report["guardrail_failures"])
        self.assertTrue(any("new_information_items" in item for item in report["major_issues"]))

    def test_normalize_review_result_blocks_lyrical_scene_without_decision_verbs(self) -> None:
        result = {
            "task_id": "scene_104",
            "verdict": "lock",
            "task_goal_fulfilled": True,
            "major_issues": [],
            "minor_issues": [],
            "recommended_next_step": "lock_scene",
            "summary": "气氛到位，可锁定。",
            "information_gain": {"has_new_information": True, "new_information_items": ["他更疲惫了。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "情绪更沉。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他心里更难受。"},
            "motif_redundancy": {"repeated_motifs": ["阿绣"], "repetition_has_new_function": True, "redundancy_reason": "有新功能。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        normalized = review_scene_module.normalize_review_result(
            result,
            "The atmosphere is strong.",
            task_text="# constraints\n- 不急于解释‘阿绣’是谁\n",
            draft_text="孟浮灯想起阿绣，喉头发紧，站在原地发怔，像是又闻见那股铁锈气。",
            based_on_text="孟浮灯想起阿绣，闻到铁锈气。",
            chapter_state="“阿绣”这个名字已经留在他心里，但目前仍只是被记住、被反复想起。",
        )

        self.assertNotEqual(normalized["verdict"], "lock")
        self.assertTrue(any("决策" in item or "动作结果" in item for item in normalized["major_issues"]))

    def test_normalize_review_result_raises_redundancy_risk_for_dense_motif_repetition(self) -> None:
        result = {
            "task_id": "scene_105",
            "verdict": "lock",
            "task_goal_fulfilled": True,
            "major_issues": [],
            "minor_issues": [],
            "recommended_next_step": "lock_scene",
            "summary": "母题复现自然。",
            "information_gain": {"has_new_information": True, "new_information_items": ["看见了红绳。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "局面略有波动。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他停了一下。"},
            "motif_redundancy": {"repeated_motifs": ["阿绣", "红绳"], "repetition_has_new_function": True, "redundancy_reason": "有新功能。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = review_scene_module.ROOT
            review_scene_module.ROOT = root
            try:
                tracker_dir = root / "03_locked/state/trackers"
                tracker_dir.mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon/ch01_state.md").write_text("- 线索推进应以轻推为主\n", encoding="utf-8")
                (tracker_dir / "ch01_chapter_motif_tracker.json").write_text(
                    '{"chapter_id": "ch01", "active_motifs": [{"motif_id": "artifact_motif_hongsheng", "category": "artifact_motif", "label": "红绳", "narrative_functions": ["过渡/氛围"], "status": "active", "recent_scene_ids": ["ch01_scene01"], "recent_usage_count": 2, "allow_next_scene": false, "only_if_new_function": true, "notes": "repeated"}, {"motif_id": "identity_motif_axiu", "category": "identity_motif", "label": "阿绣", "narrative_functions": ["过渡/氛围"], "status": "active", "recent_scene_ids": ["ch01_scene01"], "recent_usage_count": 2, "allow_next_scene": false, "only_if_new_function": true, "notes": "repeated"}]}',
                    encoding="utf-8",
                )
                (tracker_dir / "ch01_revelation_tracker.json").write_text('{"chapter_id": "ch01", "confirmed_facts": [], "suspected_facts": [], "unrevealed_facts": [], "forbidden_premature_reveals": []}', encoding="utf-8")
                (tracker_dir / "ch01_artifact_state.json").write_text('{"chapter_id": "ch01", "items": []}', encoding="utf-8")
                (tracker_dir / "ch01_chapter_progress.json").write_text('{"chapter_id": "ch01", "chapter_goal": "推进", "completed_scene_functions": [], "remaining_scene_functions": ["发现线索"], "consecutive_transition_scene_count": 1}', encoding="utf-8")

                normalized = review_scene_module.normalize_review_result(
                    result,
                    "Strong atmosphere.",
                    task_text="# task_id\n2026-04-03-017_ch01_scene02_auto\n\n# chapter_state\n03_locked/canon/ch01_state.md\n\n# constraints\n- 保持单视角\n",
                    draft_text="红绳还在晃。孟浮灯又想起阿绣，红绳贴着腕骨，阿绣两个字像铁锈一样钝痛。红绳晃了第二下，他还是只想起阿绣。",
                    based_on_text="孟浮灯看见红绳，想起阿绣。",
                    chapter_state="- 线索推进应以轻推为主\n",
                )
            finally:
                review_scene_module.ROOT = previous_root

        self.assertNotEqual(normalized["verdict"], "lock")
        self.assertTrue(any("母题" in item or "复读" in item for item in normalized["major_issues"]))

    def test_normalize_review_result_flags_chapter_state_identity_and_artifact_conflicts(self) -> None:
        result = {
            "task_id": "scene_106",
            "verdict": "lock",
            "task_goal_fulfilled": True,
            "major_issues": [],
            "minor_issues": [],
            "recommended_next_step": "lock_scene",
            "summary": "承接自然，可锁定。",
            "information_gain": {"has_new_information": True, "new_information_items": ["他摸出了平安符。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "他准备去追问。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他决定去追问。"},
            "motif_redundancy": {"repeated_motifs": ["阿绣", "平安符"], "repetition_has_new_function": True, "redundancy_reason": "有新功能。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        chapter_state = """- 阿绣尚未确认身份
- 他尚未形成调查念头，也不该主动追问这条线索
- 平安符已被藏在窝棚木板下
"""

        normalized = review_scene_module.normalize_review_result(
            result,
            "Looks fine.",
            task_text="# constraints\n- 不急于解释‘阿绣’是谁\n",
            draft_text="他把平安符从怀里摸出来，忽然记起阿绣总爱替他把领口压平，便想去追问这个名字的来处。",
            based_on_text="他把平安符塞进窝棚木板下。",
            chapter_state=chapter_state,
        )

        self.assertNotEqual(normalized["verdict"], "lock")
        self.assertTrue(any("canon" in item or "chapter_state" in item for item in normalized["major_issues"]))

    def test_normalize_review_result_merges_multi_phase_skill_audit_into_issues(self) -> None:
        result = {
            "task_id": "scene_108",
            "verdict": "revise",
            "task_goal_fulfilled": False,
            "major_issues": ["已有结构问题。"],
            "minor_issues": [],
            "recommended_next_step": "create_revision_task",
            "summary": "需要修订。",
            "information_gain": {"has_new_information": True, "new_information_items": ["确认袖里多了一张旧票。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "主角改变了交差顺序。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他决定先藏票再回屋。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无明显复读。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = review_scene_module.ROOT
            review_scene_module.ROOT = root
            try:
                planning_dir = root / "02_working/planning"
                planning_dir.mkdir(parents=True, exist_ok=True)
                (planning_dir / "skill_audit.json").write_text(
                    json.dumps(
                        {
                            "audits": [
                                {
                                    "phase": "planning_bootstrap",
                                    "selected_skills": ["worldbuilding", "scene-outline"],
                                    "major_issues": [],
                                    "minor_issues": ["planning_bootstrap router 当前启用：worldbuilding、scene-outline。"],
                                    "is_ok": True,
                                },
                                {
                                    "phase": "scene_writing",
                                    "selected_skills": ["character-design"],
                                    "major_issues": ["scene_writing router 漏选 `continuity-guard`，会带来明显连续性风险。"],
                                    "minor_issues": [],
                                    "is_ok": False,
                                },
                            ]
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                normalized = review_scene_module.normalize_review_result(
                    result,
                    raw_review_text="需要继续修订。",
                    task_text="# task_id\nscene_108\n\n# chapter_state\n03_locked/canon/ch01_state.md\n\n# output_target\n02_working/drafts/ch01_scene08.md\n",
                    low_confidence=False,
                    draft_text="孟浮灯把旧票塞进袖里，先改了回屋的步子。",
                    based_on_text="孟浮灯刚收工回屋。",
                    chapter_state="当前仍处于求活观察阶段。",
                )
            finally:
                review_scene_module.ROOT = previous_root

        self.assertFalse(any("[skill audit][" in item for item in normalized["minor_issues"]))
        self.assertFalse(any("[skill audit][" in item for item in normalized["major_issues"]))

    def test_normalize_review_result_auto_locks_when_structural_signals_are_all_green(self) -> None:
        result = {
            "task_id": "scene_109",
            "verdict": "revise",
            "task_goal_fulfilled": False,
            "major_issues": ["当前草稿未充分完成 task 的核心推进目标。"],
            "minor_issues": ["Reviewer 原始输出主要是无效英文分析，已降权处理。"],
            "recommended_next_step": "create_revision_task",
            "summary": "本场具备信息增量、情节推进、行为偏移，且未发现明显母题空转或 canon 漂移。",
            "information_gain": {"has_new_information": True, "new_information_items": ["他摸到尸体腰间多了一块冷玉。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "他因此改了交差顺序。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他先把冷玉塞进袖口。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "未识别到明显的高频母题复读。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        normalized = review_scene_module.normalize_review_result(
            result,
            raw_review_text="We need to produce a JSON object.",
            task_text="# task_id\nscene_109\n",
            low_confidence=True,
            draft_text="孟浮灯摸到尸体腰间多了一块冷玉，决定先把那东西塞进袖口，随后改了交差顺序。",
            based_on_text="孟浮灯原本只想把尸体拖上岸。",
            chapter_state="当前仍处于求活观察阶段。",
        )

        self.assertEqual(normalized["verdict"], "lock")
        self.assertEqual(normalized["recommended_next_step"], "lock_scene")
        self.assertTrue(normalized["task_goal_fulfilled"])
        self.assertEqual(normalized["major_issues"], [])

    def test_build_structural_review_signals_marks_new_function_reuse_as_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = review_scene_module.ROOT
            review_scene_module.ROOT = root
            try:
                tracker_dir = root / "03_locked/state/trackers"
                tracker_dir.mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon/ch01_state.md").write_text("章节状态", encoding="utf-8")
                (tracker_dir / "ch01_chapter_motif_tracker.json").write_text(
                    '{"chapter_id": "ch01", "active_motifs": [{"motif_id": "artifact_motif_hongsheng", "category": "artifact_motif", "label": "红绳", "narrative_functions": ["过渡/氛围"], "status": "active", "recent_scene_ids": ["ch01_scene01"], "recent_usage_count": 2, "recent_functions": ["过渡/氛围"], "last_function": "过渡/氛围", "function_novelty_score": 0.0, "allow_next_scene": false, "only_if_new_function": true, "redundancy_risk": "high", "notes": "repeated"}]}',
                    encoding="utf-8",
                )
                (tracker_dir / "ch01_revelation_tracker.json").write_text('{"chapter_id": "ch01", "confirmed_facts": [], "suspected_facts": [], "unrevealed_facts": [], "forbidden_premature_reveals": []}', encoding="utf-8")
                (tracker_dir / "ch01_artifact_state.json").write_text('{"chapter_id": "ch01", "items": []}', encoding="utf-8")
                (tracker_dir / "ch01_chapter_progress.json").write_text('{"chapter_id": "ch01", "chapter_goal": "推进", "completed_scene_functions": [], "remaining_scene_functions": ["发现线索"], "consecutive_transition_scene_count": 1}', encoding="utf-8")

                signals = review_scene_module.build_structural_review_signals(
                    task_text="# task_id\n2026-04-03-017_ch01_scene02_auto\n\n# chapter_state\n03_locked/canon/ch01_state.md\n",
                    draft_text="红绳这次露出背面刻着一个新字样，他立刻把那截红绳收进袖里。",
                    based_on_text="孟浮灯看见红绳，什么也没做。",
                    chapter_state="章节状态",
                )
            finally:
                review_scene_module.ROOT = previous_root

        self.assertIn("红绳", signals["motif_redundancy"]["repeated_motifs"])
        self.assertIn("红绳", signals["motif_redundancy"]["new_function_motifs"])
        self.assertTrue(signals["motif_redundancy"]["repetition_has_new_function"])
        self.assertTrue(signals["motif_redundancy"]["same_function_reuse_allowed"])

    def test_build_structural_review_signals_allows_same_scene_function_when_local_gain_is_new(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = review_scene_module.ROOT
            review_scene_module.ROOT = root
            try:
                tracker_dir = root / "03_locked/state/trackers"
                tracker_dir.mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon/ch01_state.md").write_text("章节状态", encoding="utf-8")
                (tracker_dir / "ch01_chapter_motif_tracker.json").write_text(
                    '{"chapter_id": "ch01", "active_motifs": [{"motif_id": "artifact_motif_hongsheng", "category": "artifact_motif", "label": "红绳", "narrative_functions": ["触发调查"], "status": "active", "recent_scene_ids": ["ch01_scene02"], "recent_usage_count": 2, "recent_functions": ["触发调查"], "last_function": "触发调查", "function_novelty_score": 0.2, "allow_next_scene": false, "only_if_new_function": true, "redundancy_risk": "high", "notes": "repeated"}]}',
                    encoding="utf-8",
                )
                (tracker_dir / "ch01_revelation_tracker.json").write_text('{"chapter_id": "ch01", "confirmed_facts": [], "suspected_facts": [], "unrevealed_facts": [], "forbidden_premature_reveals": []}', encoding="utf-8")
                (tracker_dir / "ch01_artifact_state.json").write_text('{"chapter_id": "ch01", "items": []}', encoding="utf-8")
                (tracker_dir / "ch01_chapter_progress.json").write_text('{"chapter_id": "ch01", "chapter_goal": "推进", "completed_scene_functions": [], "remaining_scene_functions": ["触发调查"], "consecutive_transition_scene_count": 1}', encoding="utf-8")

                signals = review_scene_module.build_structural_review_signals(
                    task_text="# task_id\n2026-04-03-017_ch01_scene03_auto\n\n# scene_function\n触发调查\n\n# chapter_state\n03_locked/canon/ch01_state.md\n",
                    draft_text="他把红绳放到灯下，看见绳脚磨白的一段，立刻拿油布包好，塞进里襟。",
                    based_on_text="孟浮灯昨夜已经把红绳收了起来。",
                    chapter_state="章节状态",
                )
            finally:
                review_scene_module.ROOT = previous_root

        self.assertIn("红绳", signals["motif_redundancy"]["repeated_motifs"])
        self.assertIn("红绳", signals["motif_redundancy"]["new_function_motifs"])
        self.assertTrue(signals["motif_redundancy"]["repetition_has_new_function"])
        self.assertTrue(signals["motif_redundancy"]["same_function_reuse_allowed"])


if __name__ == "__main__":
    unittest.main()
