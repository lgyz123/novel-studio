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
                        "next_task": {
                            "goal": "基于上一版草稿进行局部修补，优先收紧 POV 并压缩重复说明。",
                            "constraints": ["保持单视角", "不要扩写新主线"],
                            "preferred_length": "500-900字",
                            "repair_mode": "local_fix"
                        },
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
        self.assertEqual(decision["next_task"]["repair_mode"], "local_fix")

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
            "# task_id\nscene_071-R6\n\n# goal\n由 supervisor 生成的修订任务。\n\n# based_on\n02_working/drafts/scene_071_v5.md\n\n# chapter_state\n03_locked/canon/ch01_state.md\n\n# repair_mode\nlocal_fix\n\n# repair_plan\n02_working/reviews/scene_071-R5_repair_plan.json\n\n# constraints\n- 保持单视角\n- 不扩写新主线\n\n# output_target\n02_working/drafts/scene_071_v6.md\n",
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
                    self.assertIn("由 supervisor 生成的修订任务", task_content)
                    self.assertIn("# repair_mode\nlocal_fix", task_content)
                finally:
                    main_module.ROOT = previous_root
        finally:
            main_module.maybe_supervise_manual_decision = previous_supervisor

    def test_supervisor_task_builder_creates_followup_task_content(self) -> None:
        decision = {
            "task_id": "scene_073-R2",
            "action": "continue_rewrite",
            "reason": "当前方向偏了，应转整体重写。",
            "focus_points": ["删去错误推进线。"],
            "next_task": {
                "goal": "基于上一版草稿整体重写当前 scene，恢复单一推进目标。",
                "constraints": ["保持单视角", "不要新增调查动作"],
                "preferred_length": "600-900字",
                "repair_mode": ""
            },
        }

        content = supervisor_module.build_task_content_from_supervisor_decision(
            decision,
            "# task_id\nscene_073-R2\n\n# chapter_state\n03_locked/canon/ch01_state.md\n",
            "02_working/drafts/ch01_scene73_v3.md",
        )

        self.assertIsNotNone(content)
        self.assertIn("# task_id\nscene_073-RW1", content)
        self.assertIn("# goal\n基于上一版草稿整体重写当前 scene，恢复单一推进目标。", content)
        self.assertIn("# output_target\n02_working/drafts/ch01_scene73_v3_rewrite.md", content)

    def test_next_scene_task_content_builder_creates_scene11_task(self) -> None:
        plan = {
            "task_id": "2026-04-03-018_ch01_scene11_auto",
            "goal": "承接 ch01_scene10，写出第一章第十一个短场景，让余波继续压在求活日常里。",
            "constraints": ["保持单视角", "不要升级为明确调查"],
            "preferred_length": "500-900字",
        }

        content = supervisor_module.build_next_scene_task_content(
            plan,
            "# task_id\n2026-04-03-017-R5\n\n# chapter_state\n03_locked/canon/ch01_state.md\n",
            "03_locked/chapters/ch01_scene10.md",
        )

        self.assertIn("# task_id\n2026-04-03-018_ch01_scene11_auto", content)
        self.assertIn("# based_on\n03_locked/chapters/ch01_scene10.md", content)
        self.assertIn("# output_target\n02_working/drafts/ch01_scene11.md", content)
        self.assertIn("- 保持单视角", content)

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
        main_module.maybe_supervise_manual_decision = lambda *args, **kwargs: (None, "02_working/reviews/scene_072-R5_supervisor_decision.json", None)
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

    def test_route_review_result_lock_generates_next_scene_task_draft(self) -> None:
        task_text = """# task_id
2026-04-03-017-R5

# goal
完成 scene10。

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/ch01_scene10_v6.md
"""
        reviewer_result = {
            "task_id": "2026-04-03-017-R5",
            "verdict": "lock",
            "task_goal_fulfilled": True,
            "major_issues": [],
            "minor_issues": [],
            "recommended_next_step": "lock_scene",
            "summary": "当前 scene 可锁定。",
        }
        config = {
            "paths": {"working_dir": "02_working", "inputs_dir": "01_inputs", "locked_dir": "03_locked"},
            "generation": {"max_auto_revisions": 5},
            "supervisor": {"enabled": True},
        }

        previous_next_scene = main_module.maybe_generate_next_scene_task_draft
        main_module.maybe_generate_next_scene_task_draft = lambda *args, **kwargs: (
            "01_inputs/tasks/generated/2026-04-03-018_ch01_scene11_auto.md",
            "02_working/reviews/2026-04-03-018_ch01_scene11_auto_next_scene_task_plan.json",
        )
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                previous_root = main_module.ROOT
                main_module.ROOT = root
                try:
                    (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
                    (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                    (root / "03_locked/state/history").mkdir(parents=True, exist_ok=True)
                    (root / "02_working/drafts/ch01_scene10_v6.md").write_text("正文", encoding="utf-8")
                    (root / "03_locked/canon/ch01_state.md").write_text("章节状态", encoding="utf-8")
                    created = main_module.route_review_result(config, task_text, "02_working/drafts/ch01_scene10_v6.md", reviewer_result)
                    self.assertEqual(created["next_scene_task_file"], "01_inputs/tasks/generated/2026-04-03-018_ch01_scene11_auto.md")
                    self.assertEqual(created["next_scene_plan_file"], "02_working/reviews/2026-04-03-018_ch01_scene11_auto_next_scene_task_plan.json")
                finally:
                    main_module.ROOT = previous_root
        finally:
            main_module.maybe_generate_next_scene_task_draft = previous_next_scene


if __name__ == "__main__":
    unittest.main()
