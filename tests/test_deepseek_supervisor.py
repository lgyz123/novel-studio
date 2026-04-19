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
from pydantic import ValidationError


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
    def test_build_next_scene_task_defaults_accepts_locked_files_with_drift_suffix(self) -> None:
        task_text = "# task_id\n2026-04-03-018_ch01_scene11_auto-RW1-RW1\n"

        next_task_id, output_target = supervisor_module.build_next_scene_task_defaults(
            task_text,
            "03_locked/chapters/ch01_scene11_v3_rewrite_v8.md",
        )

        self.assertEqual(next_task_id, "2026-04-03-019_ch01_scene12_auto")
        self.assertEqual(output_target, "02_working/drafts/ch01_scene12.md")

    def test_supervisor_decision_allows_manual_intervention_without_next_task(self) -> None:
        decision = supervisor_module.SupervisorDecision.from_dict(
            {
                "task_id": "scene_069-R5",
                "action": "manual_intervention",
                "reason": "风险过高，转人工介入。",
                "focus_points": [],
            }
        )

        self.assertEqual(getattr(decision.action, "value", decision.action), "manual_intervention")
        self.assertIsNone(decision.next_task)

    def test_supervisor_decision_allows_manual_intervention_with_empty_next_task_object(self) -> None:
        decision = supervisor_module.SupervisorDecision.from_dict(
            {
                "task_id": "scene_069-R5",
                "action": "manual_intervention",
                "reason": "风险过高，转人工介入。",
                "focus_points": [],
                "next_task": {},
            }
        )

        self.assertEqual(getattr(decision.action, "value", decision.action), "manual_intervention")
        self.assertIsNone(decision.next_task)

    def test_supervisor_decision_requires_next_task_for_continue_actions(self) -> None:
        with self.assertRaises(ValidationError):
            supervisor_module.SupervisorDecision.from_dict(
                {
                    "task_id": "scene_069-R5",
                    "action": "continue_revise",
                    "reason": "还可以继续修。",
                    "focus_points": [],
                }
            )

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

    def test_supervisor_messages_include_scene10_guardrails(self) -> None:
        messages = supervisor_module.build_supervisor_messages(
            "# task_id\n2026-04-03-017-RW3\n\n# goal\n重写 scene10\n\n# output_target\n02_working/drafts/ch01_scene10_v6_rewrite3.md\n",
            {"task_id": "2026-04-03-017-RW3", "verdict": "revise"},
            {"draft_file": "02_working/drafts/ch01_scene10_v6_rewrite3.md"},
        )

        self.assertIn("scene10 专项要求", messages[0]["content"])
        self.assertIn("不要再让 next_task 回到“改结法 / 多打一个结 / 留下线头", messages[0]["content"])

    def test_supervisor_rescue_messages_include_scene10_guardrails(self) -> None:
        messages = supervisor_module.build_supervisor_rescue_messages(
            "# task_id\n2026-04-03-017-RW4\n\n# goal\n重写 scene10\n\n# output_target\n02_working/drafts/ch01_scene10_v6_rewrite4.md\n",
            "旧稿正文",
            {"task_id": "2026-04-03-017-RW3", "verdict": "revise"},
            {},
        )

        self.assertIn("scene10 专项要求", messages[0]["content"])
        self.assertIn("不是再次留下某截东西", messages[0]["content"])

    def test_supervisor_rescue_context_includes_current_context_and_scene10_strategy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "02_working/context").mkdir(parents=True, exist_ok=True)
            (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
            (root / "02_working/context/current_context.md").write_text("完整上下文", encoding="utf-8")
            (root / "02_working/drafts/scene10_old.md").write_text("旧稿正文", encoding="utf-8")
            (root / "03_locked/canon/ch01_state.md").write_text("章节状态", encoding="utf-8")

            context = supervisor_module.build_supervisor_rescue_context(
                root,
                "2026-04-03-017-RW4",
                "02_working/drafts/scene10_old.md",
                "# task_id\n2026-04-03-017-RW4\n\n# goal\n重写 scene10\n\n# chapter_state\n03_locked/canon/ch01_state.md\n\n# output_target\n02_working/drafts/ch01_scene10_v6_rewrite4.md\n",
            )

        self.assertEqual(context["current_context_text"], "完整上下文")
        self.assertIn("scene10_rescue_strategy", context)
        self.assertIn("allowed_micro_shift_examples", context["scene10_rescue_strategy"])

    def test_build_next_scene_context_includes_chapter_level_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
            (root / "02_working/reviews").mkdir(parents=True, exist_ok=True)

            (root / "03_locked/chapters/ch01_scene01.md").write_text("孟浮灯走回窝棚，只觉得寒气和铁锈味还在身上。", encoding="utf-8")
            (root / "03_locked/chapters/ch01_scene02.md").write_text("他又闻到腐臭，想起阿绣，喉头发紧，仍没有做别的动作。", encoding="utf-8")
            (root / "03_locked/chapters/ch01_scene03.md").write_text("他回到窝棚门口，寒气还贴在身上，只觉得铁锈味和阿绣两个字一起压在喉头。", encoding="utf-8")
            (root / "03_locked/canon/ch01_state.md").write_text(
                """# ch01 当前状态

## 暂不展开的内容
- 不揭示阿绣身份

## scene03 建议目标
- 继续轻推线索，但要让下一场承担不同功能
""",
                encoding="utf-8",
            )
            (root / "03_locked/state/story_state.json").write_text(
                json.dumps(
                    {
                        "characters": {
                            "protagonist": {
                                "physical_state": "疲惫",
                                "mental_state": "被阿绣牵动",
                                "known_facts": ["平安符背面有‘阿绣’"],
                                "active_goals": ["维持码头日常"],
                                "open_tensions": ["尚未形成调查念头"],
                            }
                        },
                        "unresolved_promises": [{"description": "不揭示阿绣身份"}],
                        "items": [{"name": "平安符", "status": "状态待确认"}],
                        "relationship_deltas": [{"delta": "阿绣仍只是被记住的名字"}],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            context = supervisor_module.build_next_scene_context(
                root,
                "scene_003",
                "03_locked/chapters/ch01_scene03.md",
                "# chapter_state\n03_locked/canon/ch01_state.md\n",
            )

        self.assertIn("chapter_progress", context)
        self.assertIn("scene_type_control", context)
        self.assertIn("revelation_tracker", context)
        self.assertIn("state_tracker", context)
        self.assertIn("motif_budget", context)
        self.assertEqual(context["chapter_progress"]["chapter_id"], "ch01")
        self.assertGreaterEqual(context["chapter_progress"]["consecutive_transition_scene_count"], 1)
        self.assertTrue(context["revelation_tracker"]["confirmed_facts"])
        self.assertTrue(str(context["state_tracker"]["artifact_state"]).strip())

    def test_next_scene_messages_require_structural_plan_fields(self) -> None:
        messages = supervisor_module.build_next_scene_messages(
            "# task_id\n2026-04-03-017-R5\n\n# goal\n完成 scene10。\n",
            "03_locked/chapters/ch01_scene10.md",
            {
                "task_id": "2026-04-03-017-R5",
                "motif_redundancy": {"repeated_motifs": ["阿绣", "红绳"]},
            },
            {"locked_file": "03_locked/chapters/ch01_scene10.md"},
        )

        self.assertIn('"scene_purpose": "string"', messages[0]["content"])
        self.assertIn('"scene_function": "string"', messages[0]["content"])
        self.assertIn('"required_information_gain": ["string"]', messages[0]["content"])
        self.assertIn('"decision_requirement": "string"', messages[0]["content"])
        self.assertIn('"required_state_change": ["string"]', messages[0]["content"])
        self.assertIn('"forbidden_repetition": ["string"]', messages[0]["content"])
        self.assertIn("不能只写气氛延长、余波延长或情绪回响", messages[0]["content"])
        self.assertIn("scene_type_control", messages[0]["content"])
        self.assertIn("transition / reflection` 连续不得超过 2 场", messages[0]["content"])
        self.assertIn("discovery >= 20%", messages[0]["content"])
        self.assertIn("chapter_progress", messages[0]["content"])
        self.assertIn("avoid_motifs", messages[0]["content"])

    def test_choose_scene_function_default_forces_strong_type_after_two_weak_scenes(self) -> None:
        context = {
            "chapter_progress": {
                "remaining_scene_functions": ["过渡/氛围", "发现线索", "触发调查", "引发后果"],
                "consecutive_transition_scene_count": 2,
            },
            "scene_type_control": {
                "preferred_next_scene_types": ["decision", "discovery"],
                "disallowed_next_scene_types": ["atmosphere", "transition", "reflection"],
                "weak_scene_streak_count": 2,
                "policy": {"max_consecutive_weak_scenes": 2},
            },
        }

        scene_function = supervisor_module.choose_scene_function_default(context)

        self.assertIn(scene_function, ["触发调查", "发现线索"])

    def test_build_scene_type_control_detects_quota_gap_and_weak_streak(self) -> None:
        context = {
            "chapter_progress": {
                "scene_summaries": [
                    {"scene_id": "ch01_scene01", "scene_function": "过渡/氛围", "new_information_items": [], "protagonist_decision": "", "state_changes": [], "artifacts_changed": []},
                    {"scene_id": "ch01_scene02", "scene_function": "过渡/氛围", "new_information_items": [], "protagonist_decision": "", "state_changes": [], "artifacts_changed": []},
                    {"scene_id": "ch01_scene03", "scene_function": "发现线索", "new_information_items": ["确认平安符背后多了一道刻痕。"], "protagonist_decision": "把平安符收起。", "state_changes": ["protagonist_mode: 观察/求活 -> 隐匿/压制"], "artifacts_changed": [{"label": "平安符"}]},
                    {"scene_id": "ch01_scene04", "scene_function": "过渡/氛围", "new_information_items": [], "protagonist_decision": "", "state_changes": [], "artifacts_changed": []},
                    {"scene_id": "ch01_scene05", "scene_function": "过渡/氛围", "new_information_items": [], "protagonist_decision": "", "state_changes": [], "artifacts_changed": []},
                ]
            }
        }

        control = supervisor_module.build_scene_type_control(context)

        self.assertEqual(control["weak_scene_streak_count"], 2)
        self.assertIn("decision", control["preferred_next_scene_types"])
        self.assertIn("atmosphere", control["disallowed_next_scene_types"])
        self.assertTrue(control["quota_gaps"])

    def test_build_next_scene_structural_defaults_uses_scene_type_control_when_weak_streak_hits_cap(self) -> None:
        context = {
            "chapter_progress": {
                "remaining_scene_functions": ["过渡/氛围", "发现线索", "引发后果"],
                "consecutive_transition_scene_count": 2,
            },
            "revelation_tracker": {"suspected_facts": ["阿绣与平安符有关"]},
            "scene_type_control": {
                "preferred_next_scene_types": ["consequence", "discovery"],
                "disallowed_next_scene_types": ["atmosphere", "transition", "reflection"],
                "weak_scene_streak_count": 2,
                "quota_gaps": [{"scene_type": "consequence", "current": 0, "required_by_next": 1}],
                "policy": {"max_consecutive_weak_scenes": 2},
            },
            "motif_budget": [],
        }

        defaults = supervisor_module.build_next_scene_structural_defaults(
            "# task_id\nscene_510\n\n# goal\n继续推进。\n",
            "03_locked/chapters/ch01_scene05.md",
            {"motif_redundancy": {"repeated_motifs": []}},
            context=context,
        )

        self.assertEqual(defaults["scene_function"], "引发后果")
        self.assertIn("类型配额缺口", defaults["scene_purpose"])
        self.assertTrue(any("transition / reflection / atmosphere" in item or "atmosphere / transition / reflection" in item for item in defaults["forbidden_repetition"]))

    def test_maybe_supervise_manual_decision_retries_with_recovery_prompt(self) -> None:
        task_text = """# task_id
scene_070-R5

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/scene_070_v6.md
"""
        reviewer_result = {
            "task_id": "scene_070-R5",
            "verdict": "revise",
            "major_issues": ["核心目标未完成。"],
            "minor_issues": [],
            "summary": "需要升级处理。",
        }
        config = {
            "supervisor": {"enabled": True},
            "generation": {"max_supervisor_rounds": 3},
        }

        decisions = [
            {
                "task_id": "scene_070-R5",
                "action": "manual_intervention",
                "reason": "首轮认为风险较高。",
                "focus_points": [],
            },
            {
                "task_id": "scene_070-R5",
                "action": "continue_rewrite",
                "reason": "改成整体重写仍可自动推进。",
                "focus_points": ["保留单视角，只修核心动作闭环。"],
                "next_task": {
                    "goal": "整体重写当前 scene，补足核心动作闭环。",
                    "constraints": ["保持单视角", "不要扩写主线"],
                    "preferred_length": "500-900字",
                    "repair_mode": "",
                },
            },
        ]

        previous_run = main_module.run_supervisor_decision
        main_module.run_supervisor_decision = lambda *args, **kwargs: decisions.pop(0)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                previous_root = main_module.ROOT
                main_module.ROOT = root
                try:
                    supervised_result, decision_path, task_content = main_module.maybe_supervise_manual_decision(
                        config,
                        task_text,
                        reviewer_result,
                        "02_working/drafts/scene_070_v6.md",
                        5,
                        "达到自动修订上限。",
                    )
                finally:
                    main_module.ROOT = previous_root
        finally:
            main_module.run_supervisor_decision = previous_run

        self.assertIsNotNone(supervised_result)
        self.assertEqual(supervised_result["verdict"], "rewrite")
        self.assertIsNotNone(decision_path)
        self.assertIsNotNone(task_content)
        self.assertIn("# supervisor_round\n1", task_content)
        self.assertIn("整体重写当前 scene，补足核心动作闭环。", task_content)

    def test_apply_supervisor_decision_clears_stale_manual_intervention_reason(self) -> None:
        reviewer_result = {
            "task_id": "scene_074-R4",
            "verdict": "revise",
            "summary": "已达到修订阈值，建议人工介入。",
            "major_issues": ["已达到修订阈值，建议人工介入。"],
            "minor_issues": [],
            "force_manual_intervention_reason": "已达到修订阈值，建议人工介入。",
        }
        decision = {
            "task_id": "scene_074-R4",
            "action": "continue_rewrite",
            "reason": "继续整体重写仍有收敛空间。",
            "focus_points": ["补足关键动作闭环。"],
            "next_task": {
                "goal": "整体重写当前 scene，补足关键动作闭环。",
                "constraints": ["保持单视角"],
                "preferred_length": "500-900字",
                "repair_mode": "",
            },
        }

        updated = supervisor_module.apply_supervisor_decision_to_reviewer_result(reviewer_result, decision)

        self.assertEqual(updated["verdict"], "rewrite")
        self.assertNotIn("force_manual_intervention_reason", updated)
        self.assertEqual(updated["summary"], "继续整体重写仍有收敛空间。")

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
        previous_rescue = main_module.maybe_prepare_supervisor_rescue_draft
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
        main_module.maybe_prepare_supervisor_rescue_draft = lambda *args, **kwargs: (
            "02_working/drafts/scene_071_v6.md",
            "02_working/reviews/scene_071-R6_supervisor_rescue.json",
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
                    self.assertEqual(created["supervisor_rescue_draft_file"], "02_working/drafts/scene_071_v6.md")
                    self.assertEqual(created["supervisor_rescue_record_file"], "02_working/reviews/scene_071-R6_supervisor_rescue.json")
                    task_content = task_file.read_text(encoding="utf-8")
                    self.assertIn("scene_071-R6", task_content)
                    self.assertIn("由 supervisor 生成的修订任务", task_content)
                    self.assertIn("# repair_mode\nlocal_fix", task_content)
                finally:
                    main_module.ROOT = previous_root
        finally:
            main_module.maybe_supervise_manual_decision = previous_supervisor
            main_module.maybe_prepare_supervisor_rescue_draft = previous_rescue

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
            "# task_id\nscene_073-R2\n\n# chapter_state\n03_locked/canon/ch01_state.md\n\n# supervisor_round\n1\n",
            "02_working/drafts/ch01_scene73_v3.md",
        )

        self.assertIsNotNone(content)
        self.assertIn("# task_id\nscene_073-RW1", content)
        self.assertIn("# goal\n基于上一版草稿整体重写当前 scene，恢复单一推进目标。", content)
        self.assertIn("# supervisor_round\n2", content)
        self.assertIn("# output_target\n02_working/drafts/ch01_scene73_v3_rewrite.md", content)

    def test_next_scene_task_content_builder_creates_scene11_task(self) -> None:
        plan = {
            "task_id": "2026-04-03-018_ch01_scene11_auto",
            "goal": "承接 ch01_scene10，写出第一章第十一个短场景，让余波继续压在求活日常里。",
            "scene_function": "发现线索",
            "scene_purpose": "让局面从余波停留推进到新的现实约束落地。",
            "required_information_gain": ["补充一个新的物件状态变化。"],
            "required_plot_progress": "场景结尾前必须形成新的现实阻碍。",
            "required_decision_shift": "主角必须改变原本的处理方式。",
            "decision_requirement": "主角必须先把线索收起，再决定是否处理。",
            "required_state_change": ["物件位置变化", "主角认知变化"],
            "motif_budget_for_scene": {"allowed_motifs": ["平安符"], "banned_motifs": ["红绳尾端"], "only_if_new_function": ["阿绣"]},
            "tracker_update_proposal": {
                "motif_updates": [{"op": "add_or_update", "label": "平安符"}],
                "revelation_updates": [{"op": "anticipate", "fact": "补充一个新的物件状态变化。"}],
                "artifact_state_hints": [{"op": "anticipate_change", "state_change": "物件位置变化"}],
                "progress_updates": [{"op": "plan_scene_function", "scene_function": "发现线索"}],
            },
            "forbidden_repetition": ["禁止只写疲惫+环境+联想"],
            "avoid_motifs": ["红绳尾端", "再次打结"],
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
        self.assertIn("# scene_function\n发现线索", content)
        self.assertIn("# scene_purpose\n让局面从余波停留推进到新的现实约束落地。", content)
        self.assertIn("# required_information_gain\n- 补充一个新的物件状态变化。", content)
        self.assertIn("# required_plot_progress\n场景结尾前必须形成新的现实阻碍。", content)
        self.assertIn("# required_decision_shift\n主角必须改变原本的处理方式。", content)
        self.assertIn("# decision_requirement\n主角必须先把线索收起，再决定是否处理。", content)
        self.assertIn("# required_state_change\n- 物件位置变化\n- 主角认知变化", content)
        self.assertIn("# motif_budget_for_scene\n- 允许：平安符", content)
        self.assertIn("# tracker_update_proposal\n```json", content)
        self.assertIn('"motif_updates": [', content)
        self.assertIn("# forbidden_repetition\n- 禁止只写疲惫+环境+联想", content)
        self.assertIn("# avoid_motifs\n- 红绳尾端\n- 再次打结", content)
        self.assertIn("# output_target\n02_working/drafts/ch01_scene11.md", content)
        self.assertIn("- 保持单视角", content)

    def test_run_supervisor_next_scene_task_backfills_structural_fields_for_legacy_payload(self) -> None:
        fake_client = FakeClient(
            [
                json.dumps(
                    {
                        "task_id": "2026-04-03-018_ch01_scene11_auto",
                        "goal": "承接 scene10，继续推进下一场。",
                        "constraints": ["保持单视角"],
                        "preferred_length": "500-900字",
                    },
                    ensure_ascii=False,
                )
            ]
        )
        previous_factory = supervisor_module.create_deepseek_client
        supervisor_module.create_deepseek_client = lambda api_key=None, api_key_env=None: fake_client
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                locked_file = root / "03_locked/chapters/ch01_scene10.md"
                locked_file.parent.mkdir(parents=True, exist_ok=True)
                locked_file.write_text("锁定正文", encoding="utf-8")
                (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/canon/ch01_state.md").write_text("# ch01 当前状态\n\n## 暂不展开的内容\n- 不揭示阿绣身份\n", encoding="utf-8")
                (root / "03_locked/state/story_state.json").write_text(
                    json.dumps(
                        {
                            "characters": {"protagonist": {"known_facts": ["阿绣"], "active_goals": ["维持日常"], "open_tensions": ["尚未形成调查念头"]}},
                            "unresolved_promises": [{"description": "不揭示阿绣身份"}],
                            "items": [{"name": "平安符", "status": "状态待确认"}],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )

                plan = supervisor_module.run_supervisor_next_scene_task(
                    root,
                    {"supervisor": {"enabled": True, "model": "deepseek-chat", "api_key": "test-key"}},
                    "# task_id\n2026-04-03-017-R5\n\n# goal\n完成 scene10。\n\n# chapter_state\n03_locked/canon/ch01_state.md\n",
                    "03_locked/chapters/ch01_scene10.md",
                    {
                        "task_id": "2026-04-03-017-R5",
                        "motif_redundancy": {"repeated_motifs": ["阿绣"]},
                    },
                )
        finally:
            supervisor_module.create_deepseek_client = previous_factory

        self.assertIsNotNone(plan)
        self.assertIn("scene_function", plan)
        self.assertIn("scene_purpose", plan)
        self.assertTrue(plan["required_information_gain"])
        self.assertTrue(plan["required_plot_progress"].strip())
        self.assertTrue(plan["required_decision_shift"].strip())
        self.assertTrue(plan["decision_requirement"].strip())
        self.assertTrue(plan["required_state_change"])
        self.assertIn("motif_budget_for_scene", plan)
        self.assertIn("tracker_update_proposal", plan)
        self.assertIn("revelation_updates", plan["tracker_update_proposal"])
        self.assertTrue(plan["forbidden_repetition"])
        self.assertEqual(plan["avoid_motifs"], ["阿绣"])
        self.assertTrue(any(item.startswith("本场必须产生新的信息增量") for item in plan["constraints"]))

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

    def test_route_review_result_does_not_auto_lock_after_supervisor_rescue_on_revision_threshold_only(self) -> None:
        task_text = """# task_id
scene_080-RW6

# goal
继续修订当前 scene。

# based_on
02_working/drafts/scene_080_v5.md

# chapter_state
03_locked/canon/ch01_state.md

# supervisor_round
2

# constraints
- 保持单视角

# output_target
02_working/drafts/ch01_scene80_v6.md
"""
        reviewer_result = {
            "task_id": "scene_080-RW6",
            "verdict": "revise",
            "task_goal_fulfilled": False,
            "major_issues": ["已达到修订阈值 5 轮，建议人工介入。", "当前草稿未充分完成 task 的核心推进目标。"],
            "minor_issues": [],
            "recommended_next_step": "create_revision_task",
            "summary": "已达到修订阈值 5 轮，建议人工介入。",
            "force_manual_intervention_reason": "已达到修订阈值 5 轮，建议人工介入。",
            "information_gain": {"has_new_information": True, "new_information_items": ["确认了新的物件状态。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "局面已经发生了可追踪变化。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "主角做出了新的现实动作偏移。"},
            "motif_redundancy": {"repeated_motifs": ["阿绣"], "repetition_has_new_function": True, "redundancy_reason": "母题复现承担了新的动作功能。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }
        config = {
            "paths": {"working_dir": "02_working", "inputs_dir": "01_inputs", "locked_dir": "03_locked"},
            "generation": {"max_auto_revisions": 5},
            "supervisor": {"enabled": True},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                chapter_state_path = root / "03_locked/canon/ch01_state.md"
                chapter_state_path.parent.mkdir(parents=True, exist_ok=True)
                chapter_state_path.write_text("# 已锁定场景\n- ch01_scene79\n", encoding="utf-8")

                draft_path = root / "02_working/drafts/ch01_scene80_v6.md"
                draft_path.parent.mkdir(parents=True, exist_ok=True)
                draft_path.write_text("这是通过救场后保留下来的正文。", encoding="utf-8")

                rescue_record = root / "02_working/reviews/scene_080-RW6_supervisor_rescue.json"
                rescue_record.parent.mkdir(parents=True, exist_ok=True)
                rescue_record.write_text('{"task_id": "scene_080-RW6", "draft_text": "这是救场稿。"}', encoding="utf-8")

                save_structured_review_result(root, reviewer_result)
                created = main_module.route_review_result(config, task_text, "02_working/drafts/ch01_scene80_v6.md", reviewer_result)

                self.assertNotIn("locked_file", created)
                self.assertIn("manual_intervention_file", created)
            finally:
                main_module.ROOT = previous_root

    def test_route_review_result_auto_locks_after_supervisor_rescue_only_for_explicit_no_actionable_fix_reason(self) -> None:
        task_text = """# task_id
scene_081-RW6

# goal
继续修订当前 scene。

# based_on
02_working/drafts/scene_081_v5.md

# chapter_state
03_locked/canon/ch01_state.md

# supervisor_round
2

# constraints
- 保持单视角

# output_target
02_working/drafts/ch01_scene81_v6.md
"""
        reviewer_result = {
            "task_id": "scene_081-RW6",
            "verdict": "revise",
            "task_goal_fulfilled": False,
            "major_issues": ["reviewer 未继续给出可执行修订任务"],
            "minor_issues": [],
            "recommended_next_step": "create_revision_task",
            "summary": "reviewer 未继续给出可执行修订任务",
            "force_manual_intervention_reason": "reviewer 未继续给出可执行修订任务",
            "information_gain": {"has_new_information": True, "new_information_items": ["确认了新的物件状态。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "局面已经发生了可追踪变化。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "主角做出了新的现实动作偏移。"},
            "motif_redundancy": {"repeated_motifs": ["阿绣"], "repetition_has_new_function": True, "redundancy_reason": "母题复现承担了新的动作功能。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }
        config = {
            "paths": {"working_dir": "02_working", "inputs_dir": "01_inputs", "locked_dir": "03_locked"},
            "generation": {"max_auto_revisions": 5},
            "supervisor": {"enabled": True},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                chapter_state_path = root / "03_locked/canon/ch01_state.md"
                chapter_state_path.parent.mkdir(parents=True, exist_ok=True)
                chapter_state_path.write_text("# 已锁定场景\n- ch01_scene80\n", encoding="utf-8")

                draft_path = root / "02_working/drafts/ch01_scene81_v6.md"
                draft_path.parent.mkdir(parents=True, exist_ok=True)
                draft_path.write_text("这是通过救场后保留下来的正文。", encoding="utf-8")

                rescue_record = root / "02_working/reviews/scene_081-RW6_supervisor_rescue.json"
                rescue_record.parent.mkdir(parents=True, exist_ok=True)
                rescue_record.write_text('{"task_id": "scene_081-RW6", "draft_text": "这是救场稿。"}', encoding="utf-8")

                save_structured_review_result(root, reviewer_result)
                created = main_module.route_review_result(config, task_text, "02_working/drafts/ch01_scene81_v6.md", reviewer_result)

                self.assertIn("locked_file", created)
                self.assertNotIn("manual_intervention_file", created)
                self.assertEqual(created["locked_file"], "03_locked/chapters/ch01_scene81.md")
                self.assertTrue((root / created["locked_file"]).exists())
                self.assertIn("lock_gate_report_file", created)

                structured = load_structured_review_result(root, "scene_081-RW6")
                self.assertEqual(structured.status, ReviewStatus.lock)
                self.assertIn("supervisor 已完成救场", structured.summary)
            finally:
                main_module.ROOT = previous_root

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
            "information_gain": {"has_new_information": True, "new_information_items": ["确认了一个新的物件状态。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "本场局面已推进。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "主角做出了新的现实动作偏移。"},
            "motif_redundancy": {"repeated_motifs": ["阿绣"], "repetition_has_new_function": True, "redundancy_reason": "母题复现触发了新的动作。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
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
                    self.assertIn("chapter_motif_tracker_file", created)
                    self.assertIn("revelation_tracker_file", created)
                    self.assertIn("artifact_state_file", created)
                    self.assertIn("chapter_progress_file", created)
                    self.assertTrue((root / created["chapter_motif_tracker_file"]).exists())
                    self.assertTrue((root / created["revelation_tracker_file"]).exists())
                finally:
                    main_module.ROOT = previous_root
        finally:
            main_module.maybe_generate_next_scene_task_draft = previous_next_scene


if __name__ == "__main__":
    unittest.main()
