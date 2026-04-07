import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import app.review_scene as review_scene_module


class ReviewSceneSanitizationTest(unittest.TestCase):
    def test_build_review_prompt_marks_based_on_as_reference_only(self) -> None:
        prompt = review_scene_module.build_review_prompt(
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


if __name__ == "__main__":
    unittest.main()
