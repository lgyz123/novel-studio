import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import app.deepseek_supervisor as supervisor_module
import app.main as main_module
from app.review_models import ReviewStatus, load_structured_review_result, save_structured_review_result


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls = 0

    def create(self, **_: object) -> FakeResponse:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(str(outcome))


class FakeClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.chat = type("Chat", (), {"completions": FakeCompletions(outcomes)})()


class DeepSeekSupervisorTest(unittest.TestCase):
    def test_run_supervisor_decision_returns_validated_decision(self) -> None:
        fake_client = FakeClient(
            [
                json.dumps(
                    {
                        "task_id": "scene_070-R5",
                        "action": "continue_revise",
                        "reason": "repair_plan 仍然明确，允许再执行一轮定向修订。",
                        "focus_points": ["优先收紧第2段 POV。"],
                    },
                    ensure_ascii=False,
                )
            ]
        )
        previous_factory = supervisor_module.create_deepseek_client
        supervisor_module.create_deepseek_client = lambda api_key=None, api_key_env=None: fake_client
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                decision = supervisor_module.run_supervisor_decision(
                    Path(tmp_dir),
                    {"supervisor": {"enabled": True, "model": "deepseek-chat", "api_key": "test-key"}},
                    "# task_id\nscene_070-R5\n",
                    {"task_id": "scene_070-R5", "verdict": "revise", "major_issues": [], "minor_issues": [], "summary": "需要继续修订。"},
                    "02_working/drafts/scene_070_v5.md",
                    5,
                    "重复问题未收敛：style",
                )
        finally:
            supervisor_module.create_deepseek_client = previous_factory

        self.assertEqual(getattr(decision["action"], "value", decision["action"]), "continue_revise")
        self.assertEqual(decision["task_id"], "scene_070-R5")
        self.assertEqual(decision["focus_points"], ["优先收紧第2段 POV。"])

    def test_route_review_result_uses_supervisor_instead_of_human(self) -> None:
        task_text = """# task_id
scene_071-R5

# goal
继续修订当前 scene。

# based_on
02_working/drafts/scene_071_v5.md

# chapter_state
03_locked/canon/ch01_state.md

# constraints
- 保持单视角

# output_target
02_working/drafts/scene_071_v6.md
"""
        reviewer_result = {
            "task_id": "scene_071-R5",
            "verdict": "revise",
            "task_goal_fulfilled": False,
            "major_issues": ["重复问题未收敛：style"],
            "minor_issues": [],
            "recommended_next_step": "create_revision_task",
            "summary": "重复问题未收敛：style",
            "force_manual_intervention_reason": "重复问题未收敛：style",
        }
        config = {
            "paths": {"working_dir": "02_working", "inputs_dir": "01_inputs", "locked_dir": "03_locked"},
            "generation": {"max_auto_revisions": 5},
            "supervisor": {"enabled": True},
        }

        previous_supervisor = main_module.maybe_supervise_manual_decision
        main_module.maybe_supervise_manual_decision = lambda *args, **kwargs: (
            {
                "task_id": "scene_071-R5",
                "verdict": "revise",
                "task_goal_fulfilled": False,
                "major_issues": ["先修复重复问题，再压缩说明段落。"],
                "minor_issues": [],
                "recommended_next_step": "create_revision_task",
                "summary": "允许再执行一轮定向修订。",
            },
            "02_working/reviews/scene_071-R5_supervisor_decision.json",
        )
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                previous_root = main_module.ROOT
                main_module.ROOT = root
                try:
                    created = main_module.route_review_result(config, task_text, "02_working/drafts/scene_071_v5.md", reviewer_result)
                    task_file = root / created["task_file"]
                    self.assertTrue(task_file.exists())
                    self.assertNotIn("manual_intervention_file", created)
                    self.assertEqual(created["supervisor_decision_file"], "02_working/reviews/scene_071-R5_supervisor_decision.json")
                    task_content = task_file.read_text(encoding="utf-8")
                    self.assertIn("scene_071-R6", task_content)
                    self.assertIn("允许再执行一轮定向修订", task_content)
                finally:
                    main_module.ROOT = previous_root
        finally:
            main_module.maybe_supervise_manual_decision = previous_supervisor

    def test_route_review_result_keeps_manual_intervention_when_supervisor_declines(self) -> None:
        task_text = """# task_id
scene_072-R5

# goal
继续修订当前 scene。

# based_on
02_working/drafts/scene_072_v5.md

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/scene_072_v6.md
"""
        reviewer_result = {
            "task_id": "scene_072-R5",
            "verdict": "revise",
            "task_goal_fulfilled": False,
            "major_issues": ["重复问题未收敛：timeline"],
            "minor_issues": [],
            "recommended_next_step": "create_revision_task",
            "summary": "重复问题未收敛：timeline",
            "force_manual_intervention_reason": "重复问题未收敛：timeline",
        }
        config = {
            "paths": {"working_dir": "02_working", "inputs_dir": "01_inputs", "locked_dir": "03_locked"},
            "generation": {"max_auto_revisions": 5},
            "supervisor": {"enabled": True},
        }

        previous_supervisor = main_module.maybe_supervise_manual_decision
        main_module.maybe_supervise_manual_decision = lambda *args, **kwargs: (None, "02_working/reviews/scene_072-R5_supervisor_decision.json")
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                previous_root = main_module.ROOT
                main_module.ROOT = root
                try:
                    save_structured_review_result(root, reviewer_result)
                    created = main_module.route_review_result(config, task_text, "02_working/drafts/scene_072_v5.md", reviewer_result)
                    self.assertIn("manual_intervention_file", created)
                    self.assertIn("supervisor_decision_file", created)
                    structured = load_structured_review_result(root, "scene_072-R5")
                    self.assertEqual(structured.status, ReviewStatus.manual_intervention)
                finally:
                    main_module.ROOT = previous_root
        finally:
            main_module.maybe_supervise_manual_decision = previous_supervisor


if __name__ == "__main__":
    unittest.main()
