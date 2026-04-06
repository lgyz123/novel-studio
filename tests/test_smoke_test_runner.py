import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.smoke_test_runner import run_five_scene_smoke_test


class SmokeTestRunnerTest(unittest.TestCase):
    def test_run_five_scene_smoke_test_processes_all_scenes_and_writes_artifacts(self) -> None:
        outcomes = {
            "smoke_scene_01-R1": {
                "task_id": "smoke_scene_01-R1",
                "status": "lock",
                "summary": "当前场景满足锁定条件。",
                "issues": [],
                "strengths": ["目标完成。"],
                "decision_reason": "无阻塞问题。",
            },
            "smoke_scene_02-R1": {
                "task_id": "smoke_scene_02-R1",
                "status": "revise",
                "summary": "场景方向正确，但闭环仍偏弱。",
                "issues": [
                    {
                        "id": "ISSUE-001",
                        "type": "scene_purpose",
                        "severity": "high",
                        "scope": "scene",
                        "target": "smoke_scene_02-R1",
                        "message": "场景尾部闭环偏弱。",
                        "suggested_action": "rewrite_local",
                    }
                ],
                "strengths": ["整体方向可用。"],
                "decision_reason": "还需要一轮小修。",
            },
            "smoke_scene_03-R1": {
                "task_id": "smoke_scene_03-R1",
                "status": "manual_intervention",
                "summary": "DeepSeek reviewer 输出不可用，转人工介入。",
                "issues": [],
                "strengths": [],
                "decision_reason": "DeepSeek reviewer JSON 解析失败：Expecting value: line 1 column 1 (char 0)",
            },
            "smoke_scene_04-R1": {
                "task_id": "smoke_scene_04-R1",
                "status": "manual_intervention",
                "summary": "DeepSeek reviewer 输出不可用，转人工介入。",
                "issues": [],
                "strengths": [],
                "decision_reason": "DeepSeek reviewer schema 校验失败：status field invalid",
            },
        }

        def fake_reviewer(scene_text: str, scene_metadata: dict, canon_context: dict) -> dict:
            task_id = scene_metadata["task_id"]
            if task_id == "smoke_scene_05-R1":
                raise RuntimeError("temporary network issue")
            return outcomes[task_id]

        with tempfile.TemporaryDirectory() as tmp_dir:
            summary = run_five_scene_smoke_test(Path(tmp_dir), reviewer_fn=fake_reviewer)

            self.assertEqual(summary["processed_scene_count"], 5)
            self.assertEqual(summary["counts"]["lock"], 1)
            self.assertEqual(summary["counts"]["revise"], 1)
            self.assertEqual(summary["counts"]["manual_intervention"], 3)
            self.assertEqual(summary["counts"]["json_parse_failures"], 1)
            self.assertEqual(summary["counts"]["schema_failures"], 1)
            self.assertEqual(summary["uncaught_exception_count"], 1)

            allowed_statuses = {"lock", "revise", "rewrite", "manual_intervention"}
            for scene in summary["scene_results"]:
                self.assertIn(scene["final_status"], allowed_statuses)
                self.assertTrue(Path(scene["review_result_path"]).suffix == ".json")

            self.assertTrue(Path(summary["per_scene_summary_path"]).exists())
            self.assertTrue(Path(summary["overall_summary_path"]).exists())


if __name__ == "__main__":
    unittest.main()
