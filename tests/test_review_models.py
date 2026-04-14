import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.main import (
    build_existing_draft_result,
    choose_repair_focus,
    compile_context,
    build_generated_task_content,
    build_locked_chapter_file,
    build_validation_errors,
    call_writer_model,
    clean_model_output,
    contains_script_style,
    detect_scene10_old_pattern_reuse,
    build_writer_user_prompt,
    extract_supervisor_round,
    has_supervisor_retry_budget,
    maybe_prepare_supervisor_rescue_draft,
    should_use_deepseek_writer,
    should_continue_after_lock,
    write_draft,
)
from app.review_models import (
    RepairMode,
    ReviewIssue,
    ReviewScope,
    ReviewSeverity,
    ReviewStatus,
    StructuredReviewResult,
    build_repair_plan,
    build_review_result_path,
    build_structured_review_result,
    load_structured_review_result,
    load_repair_plan,
    save_repair_plan,
    save_structured_review_result,
    update_structured_review_status,
)


class ReviewModelsTest(unittest.TestCase):
    def test_should_use_deepseek_writer_when_provider_is_configured(self) -> None:
        config = {
            "writer": {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com",
            }
        }

        self.assertTrue(should_use_deepseek_writer(config))

    def test_call_writer_model_uses_deepseek_client(self) -> None:
        import app.main as main_module

        captured: dict[str, object] = {}

        class FakeCompletions:
            def create(self, **kwargs: object):
                captured.update(kwargs)

                class FakeMessage:
                    content = "生成的正文"

                class FakeChoice:
                    message = FakeMessage()

                class FakeResponse:
                    choices = [FakeChoice()]

                return FakeResponse()

        class FakeOpenAI:
            def __init__(self, api_key: str, base_url: str) -> None:
                captured["api_key"] = api_key
                captured["base_url"] = base_url
                self.chat = type("Chat", (), {"completions": FakeCompletions()})()

        previous_openai = main_module.OpenAI
        try:
            main_module.OpenAI = FakeOpenAI
            content = call_writer_model(
                {
                    "writer": {
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "base_url": "https://api.deepseek.com",
                        "api_key_env": "sk-test-key",
                    },
                    "generation": {
                        "request_timeout": 30,
                        "write_num_ctx": 2048,
                    },
                },
                "system prompt",
                "user prompt",
                temperature=0.3,
                num_predict=1200,
            )
        finally:
            main_module.OpenAI = previous_openai

        self.assertEqual(content, "生成的正文")
        self.assertEqual(captured["api_key"], "sk-test-key")
        self.assertEqual(captured["base_url"], "https://api.deepseek.com")
        self.assertEqual(captured["model"], "deepseek-chat")
        self.assertEqual(captured["messages"][0]["role"], "system")
        self.assertEqual(captured["messages"][1]["role"], "user")
        self.assertEqual(captured["max_tokens"], 1200)

    def test_writer_system_prompt_only_requests_markdown_prose(self) -> None:
        prompt = Path("/Users/guan/git/novel-studio/prompts/writer_system.md").read_text(encoding="utf-8")

        self.assertIn("只生成一个可直接保存的 Markdown 草稿正文", prompt)
        self.assertIn("只允许输出 Markdown 草稿正文", prompt)
        self.assertIn("修订说明", prompt)
        self.assertIn("required_information_gain", prompt)
        self.assertIn("avoid_motifs", prompt)
        self.assertIn("至少一个状态变量必须与开头不同", prompt)
        self.assertIn("至少命中以下三项中的两项", prompt)
        self.assertNotIn("第一部分：JSON", prompt)

    def test_validation_rejects_editorial_tail_blocks(self) -> None:
        draft = """孟浮灯把麻绳搭回肩头，顺着冷风往前走。

**修订说明**
1. 强化了疲惫感
2. 收紧了疑问推进
"""

        errors = build_validation_errors("# task_id\nscene_001\n", draft)

        self.assertTrue(any("说明性附加文本" in item for item in errors))
        self.assertTrue(any("修订说明" in item or "**修订说明**" in item for item in errors))

    def test_clean_model_output_truncates_editorial_tail_blocks(self) -> None:
        raw = """孟浮灯把门关上，潮气还贴在手背上。

【执行说明】
1. 保留环境压迫感
2. 不让疑问升级为行动
"""

        cleaned = clean_model_output(raw)

        self.assertEqual(cleaned, "孟浮灯把门关上，潮气还贴在手背上。")

    def test_build_generated_task_content_prefers_configured_length_override(self) -> None:
        task_text = """# task_id
scene_200

# goal
继续写当前 scene

# preferred_length
500-900字

# constraints
- 保持单视角
"""
        reviewer_result = {
            "summary": "需要整体重写。",
            "major_issues": ["推进不足。"],
            "minor_issues": [],
            "information_gain": {"has_new_information": True, "new_information_items": ["他确认袖口里夹着一张旧票。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "他决定不立刻交差。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "他先把旧票藏起来。"},
            "motif_redundancy": {"repeated_motifs": [], "repetition_has_new_function": True, "redundancy_reason": "无重复风险。"},
            "canon_consistency": {"is_consistent": True, "consistency_issues": []},
        }

        content = build_generated_task_content(
            task_text,
            reviewer_result,
            "02_working/drafts/scene_200.md",
            "rewrite",
            config={"generation": {"preferred_length_override": "2000-3600字"}},
        )

        self.assertIn("# preferred_length\n2000-3600字", content)
        self.assertNotIn("# preferred_length\n500-900字", content)

    def test_build_existing_draft_result_skips_when_review_is_newer(self) -> None:
        import app.main as main_module

        task_text = """# task_id
scene_201

# output_target
02_working/drafts/scene_201.md
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            draft_path = root / "02_working/drafts/scene_201.md"
            reviewer_path = root / "02_working/reviews/scene_201_reviewer.json"
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            reviewer_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text("draft", encoding="utf-8")
            reviewer_path.write_text("{}", encoding="utf-8")

            draft_timestamp = 100
            reviewer_timestamp = 200
            draft_path.touch()
            reviewer_path.touch()
            draft_path.chmod(0o644)
            reviewer_path.chmod(0o644)
            import os
            os.utime(draft_path, (draft_timestamp, draft_timestamp))
            os.utime(reviewer_path, (reviewer_timestamp, reviewer_timestamp))

            previous_root = main_module.ROOT
            try:
                main_module.ROOT = root
                result = build_existing_draft_result(task_text)
            finally:
                main_module.ROOT = previous_root

        self.assertIsNone(result)

    def test_build_existing_draft_result_reuses_when_draft_is_newer(self) -> None:
        import app.main as main_module
        import os

        task_text = """# task_id
scene_202

# output_target
02_working/drafts/scene_202.md
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            draft_path = root / "02_working/drafts/scene_202.md"
            reviewer_path = root / "02_working/reviews/scene_202_reviewer.json"
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            reviewer_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text("draft", encoding="utf-8")
            reviewer_path.write_text("{}", encoding="utf-8")

            reviewer_timestamp = 100
            draft_timestamp = 200
            os.utime(reviewer_path, (reviewer_timestamp, reviewer_timestamp))
            os.utime(draft_path, (draft_timestamp, draft_timestamp))

            previous_root = main_module.ROOT
            try:
                main_module.ROOT = root
                result = build_existing_draft_result(task_text)
            finally:
                main_module.ROOT = previous_root

        self.assertIsNotNone(result)
        self.assertEqual(result["draft_file"], "02_working/drafts/scene_202.md")

    def test_invalid_issue_category_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ReviewIssue(
                id="ISSUE-001",
                type="bad_type",
                severity="high",
                scope="scene",
                target="scene_001",
                message="bad",
                suggested_action="rewrite_local",
            )

        with self.assertRaises(ValidationError):
            ReviewIssue(
                id="ISSUE-001",
                type="style",
                severity="bad_severity",
                scope="scene",
                target="scene_001",
                message="bad",
                suggested_action="rewrite_local",
            )

    def test_save_and_load_structured_review_result(self) -> None:
        legacy_result = {
            "task_id": "scene_012_draft_03",
            "verdict": "revise",
            "summary": "当前方向正确，但动作牵引仍不够明确。",
            "major_issues": ["动作牵引不够明确，导致场景功能未完全成立。"],
            "minor_issues": ["部分句子略显冗长，需精简。"],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            rel_path = save_structured_review_result(root, legacy_result)
            self.assertEqual(rel_path, build_review_result_path("scene_012_draft_03"))

            loaded = load_structured_review_result(root, "scene_012_draft_03")
            self.assertEqual(loaded.status, ReviewStatus.revise)
            self.assertEqual(len(loaded.issues), 2)
            self.assertEqual(loaded.issues[0].severity, ReviewSeverity.high)
            self.assertEqual(loaded.issues[0].scope, ReviewScope.scene)
            self.assertEqual(loaded.issues[0].message, "动作牵引不够明确，导致场景功能未完全成立。")

    def test_manual_intervention_status_update(self) -> None:
        legacy_result = {
            "task_id": "scene_020-R5",
            "verdict": "revise",
            "summary": "仍需继续修订。",
            "major_issues": ["核心推进不足。"],
            "minor_issues": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            save_structured_review_result(root, legacy_result)
            update_structured_review_status(root, "scene_020-R5", ReviewStatus.manual_intervention, "已达自动修订上限，转人工介入。")
            loaded = load_structured_review_result(root, "scene_020-R5")
            self.assertEqual(loaded.status, ReviewStatus.manual_intervention)
            self.assertEqual(loaded.summary, "已达自动修订上限，转人工介入。")
            self.assertEqual(loaded.decision_reason, "已达自动修订上限，转人工介入。")

    def test_downstream_can_read_status_and_issues(self) -> None:
        legacy_result = {
            "task_id": "scene_030",
            "verdict": "lock",
            "summary": "当前 scene 已满足锁定条件。",
            "major_issues": [],
            "minor_issues": ["个别句子还能再压一压。"],
        }
        structured = build_structured_review_result(legacy_result)

        self.assertEqual(structured.status, ReviewStatus.lock)
        self.assertEqual(structured.issues[0].message, "个别句子还能再压一压。")
        self.assertEqual(structured.issues[0].severity, ReviewSeverity.medium)

    def test_repair_plan_prefers_local_fix_for_small_local_issues(self) -> None:
        legacy_result = {
            "task_id": "scene_040",
            "verdict": "revise",
            "summary": "整体方向正确，仅有局部润色问题。",
            "major_issues": [],
            "minor_issues": ["第2段说明略显重复，需精简。", "第7段视角稍松，可再收紧。"],
        }
        structured = build_structured_review_result(legacy_result)
        plan = build_repair_plan(structured)

        self.assertEqual(plan.mode, RepairMode.local_fix)
        self.assertEqual(len(plan.actions), 2)
        self.assertEqual(plan.actions[0].issue_id, "ISSUE-001")
        self.assertTrue(plan.actions[0].instruction)

    def test_repair_plan_escalates_to_full_redraft_for_blocking_issue(self) -> None:
        legacy_result = {
            "task_id": "scene_041",
            "verdict": "revise",
            "summary": "核心推进未完成，需要重构当前 scene。",
            "major_issues": ["核心推进未完成，导致本场 scene 功能失效。"],
            "minor_issues": [],
        }
        structured = build_structured_review_result(legacy_result)
        plan = build_repair_plan(structured)

        self.assertEqual(plan.mode, RepairMode.full_redraft)
        self.assertEqual(plan.actions[0].action, "rewrite_local_block")

    def test_repair_plan_save_and_load(self) -> None:
        legacy_result = {
            "task_id": "scene_042",
            "verdict": "revise",
            "summary": "需要处理局部问题。",
            "major_issues": ["第4段动作牵引不够明确。"],
            "minor_issues": ["第7段解释略重复。"],
        }
        structured = build_structured_review_result(legacy_result)

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            rel_path = save_repair_plan(root, structured)
            loaded = load_repair_plan(root, "scene_042")

            self.assertEqual(rel_path, "02_working/reviews/scene_042_repair_plan.json")
            self.assertEqual(loaded.task_id, "scene_042")
            self.assertGreaterEqual(len(loaded.actions), 1)

    def test_generated_revision_task_includes_repair_plan_metadata(self) -> None:
        legacy_result = {
            "task_id": "scene_043",
            "verdict": "revise",
            "summary": "需要处理局部动作与冗余。",
            "major_issues": ["第4段动作牵引不够明确。"],
            "minor_issues": ["第7段解释略重复。"],
        }
        structured = build_structured_review_result(legacy_result)
        task_text = """# task_id
scene_043

# goal
延续当前 scene。

# constraints
- 保持单视角

# output_target
02_working/drafts/ch01_scene10.md
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            save_repair_plan(root, structured)

            import app.main as main_module

            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                content = build_generated_task_content(
                    task_text,
                    {"summary": legacy_result["summary"], "major_issues": legacy_result["major_issues"], "minor_issues": legacy_result["minor_issues"]},
                    "02_working/drafts/ch01_scene10.md",
                    "revise",
                )
            finally:
                main_module.ROOT = previous_root

            self.assertIn("# repair_mode", content)
            self.assertIn("partial_redraft", content)
            self.assertIn("# repair_plan", content)
            self.assertIn("scene_043_repair_plan.json", content)

    def test_writer_prompt_includes_repair_plan_guidance(self) -> None:
        legacy_result = {
            "task_id": "scene_044",
            "verdict": "revise",
            "summary": "处理局部 POV 与重复问题。",
            "major_issues": [],
            "minor_issues": ["第2段视角略松，需要收紧。", "第6段解释重复，需精简。"],
        }
        structured = build_structured_review_result(legacy_result)
        task_text = """# task_id
scene_044

# goal
修订当前 scene。

# repair_mode
local_fix

# repair_focus
prose_repair

# repair_plan
02_working/reviews/scene_044_repair_plan.json
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            save_repair_plan(root, structured)

            import app.main as main_module

            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                prompt = build_writer_user_prompt(
                    task_text,
                    "上下文内容",
                    {"task_id": "scene_044", "goal": "修订当前 scene", "draft_file": "02_working/drafts/scene_044.md"},
                )
            finally:
                main_module.ROOT = previous_root

            self.assertIn("【修订执行计划】", prompt)
            self.assertIn("repair_mode: local_fix", prompt)
            self.assertIn("repair_focus: prose_repair", prompt)
            self.assertIn("scene_044_repair_plan.json", prompt)
            self.assertIn("本次是局部修补，不要推倒整场重写", prompt)
            self.assertIn("必须优先处理的修订动作", prompt)

    def test_writer_prompt_includes_scene10_anti_pattern_guardrails(self) -> None:
        task_text = """# task_id
2026-04-03-017-RW3
# goal
重写 scene10。

# based_on
02_working/drafts/ch01_scene10_v6_rewrite2.md

# output_target
02_working/drafts/ch01_scene10_v6_rewrite3.md
"""

        prompt = build_writer_user_prompt(
            task_text,
            "上下文内容",
            {"task_id": "2026-04-03-017-RW3", "goal": "重写 scene10", "draft_file": "02_working/drafts/ch01_scene10_v6_rewrite3.md"},
        )

        self.assertIn("【scene10 专项防跑偏规则】", prompt)
        self.assertIn("禁止再次把“改结法”", prompt)
        self.assertIn("顺手收起、没有立刻擦掉、额外确认、轻微避开、重新摆正、暂缓一个本可立即完成的收尾动作", prompt)

    def test_writer_prompt_includes_structural_scene_requirements(self) -> None:
        task_text = """# task_id
2026-04-03-018_ch01_scene11_auto

# goal
承接上一场，完成下一场 scene。

# scene_purpose
让局面从余波停留推进到新的现实约束落地。

# required_information_gain
- 补充一个新的物件状态变化。
- 明确一个新的行动边界。

# required_plot_progress
场景结尾前必须形成新的现实阻碍。

# required_decision_shift
主角必须改变原本的处理方式。

# required_state_change
- 风险等级必须变化。

# avoid_motifs
- 红绳尾端
- 再次打结
"""

        prompt = build_writer_user_prompt(
            task_text,
            "上下文内容",
            {"task_id": "2026-04-03-018_ch01_scene11_auto", "goal": "承接上一场，完成下一场 scene。"},
        )

        self.assertIn("【本场结构硬约束】", prompt)
        self.assertIn("场景功能：让局面从余波停留推进到新的现实约束落地。", prompt)
        self.assertIn("必须写出的新信息增量", prompt)
        self.assertIn("必须完成的局面推进：场景结尾前必须形成新的现实阻碍。", prompt)
        self.assertIn("主角必须出现的新动作/决策偏移：主角必须改变原本的处理方式。", prompt)
        self.assertIn("本场必须落地的状态变化", prompt)
        self.assertIn("本场避免原样复用的母题/触发物", prompt)

    def test_writer_prompt_includes_hard_progress_obligations(self) -> None:
        task_text = """# task_id
2026-04-07-020_ch01_scene12_auto

# goal
承接上一场，写出疲惫、环境与联想下仍然发生真实推进的一场。

# scene_purpose
让主角在低烈度状态下仍被迫交出新的现实变化。
"""

        prompt = build_writer_user_prompt(
            task_text,
            "上下文内容",
            {"task_id": "2026-04-07-020_ch01_scene12_auto", "goal": "承接上一场推进。"},
        )

        self.assertIn("至少一个状态变量必须与开头不同", prompt)
        self.assertIn("本场至少要有一个动作带来现实后果", prompt)
        self.assertIn("本场必须至少命中以下三项中的两项", prompt)
        self.assertIn("名字再次浮现、疑问沉入心里、身体疲惫蔓延、某物硌在胸口/掌心", prompt)
        self.assertIn("不要顺着旧 scene 正文的文风滑行", prompt)

    def test_writer_prompt_defaults_to_continuity_guard(self) -> None:
        task_text = """# task_id
2026-04-14-100_ch01_scene01_auto

# goal
承接上一场继续写。

# output_target
02_working/drafts/ch01_scene01.md
"""

        prompt = build_writer_user_prompt(
            task_text,
            "上下文内容",
            {"task_id": "2026-04-14-100_ch01_scene01_auto", "goal": "承接上一场继续写。"},
        )

        self.assertIn("本轮默认启用 `continuity-guard`", prompt)
        self.assertIn("# scene writing skill router", prompt)
        self.assertIn("# 默认写作 skill：continuity-guard", prompt)
        self.assertIn("skills/continuity-guard/SKILL.md", prompt)

    def test_compile_context_prefers_structured_inputs_and_small_prose_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            for rel_dir in [
                "00_manifest",
                "01_inputs/tasks",
                "01_inputs/life_notes",
                "02_working/context",
                "02_working/drafts",
                "03_locked/canon",
                "03_locked/state/trackers",
                "03_locked/state",
            ]:
                (root / rel_dir).mkdir(parents=True, exist_ok=True)

            (root / "00_manifest/novel_manifest.md").write_text("总纲", encoding="utf-8")
            (root / "00_manifest/world_bible.md").write_text("世界设定", encoding="utf-8")
            (root / "00_manifest/character_bible.md").write_text("### 孟浮灯\n- 核心视角人物", encoding="utf-8")
            (root / "01_inputs/life_notes/latest.md").write_text("潮气、疲惫、风声", encoding="utf-8")
            (root / "01_inputs/tasks/current_task.md").write_text(
                """# task_id
2026-04-07-021_ch01_scene04_auto

# goal
承接上一场，完成一次真实推进。

# scene_purpose
让主角因为物件状态变化而进入新的处理阶段。

# required_information_gain
- 确认平安符位置已变化。

# chapter_state
03_locked/canon/ch01_state.md

# based_on
02_working/drafts/ch01_scene03.md

# output_target
02_working/drafts/ch01_scene04.md
""",
                encoding="utf-8",
            )
            (root / "03_locked/canon/ch01_state.md").write_text("## 暂不展开的内容\n- 阿绣关系暂不揭穿\n", encoding="utf-8")
            (root / "02_working/drafts/ch01_scene03.md").write_text(
                "开头旧稿气氛" * 120 + "\n结尾参考：他把平安符压回袖里，听见风从棚屋缝里钻过去。",
                encoding="utf-8",
            )
            (root / "03_locked/state/story_state.json").write_text(json.dumps({"characters": {"protagonist": {"active_goals": ["查清平安符来处"]}}}, ensure_ascii=False, indent=2), encoding="utf-8")
            (root / "03_locked/state/trackers/ch01_chapter_motif_tracker.json").write_text(json.dumps({"chapter_id": "ch01", "active_motifs": []}, ensure_ascii=False, indent=2), encoding="utf-8")
            (root / "03_locked/state/trackers/ch01_revelation_tracker.json").write_text(
                json.dumps(
                    {
                        "chapter_id": "ch01",
                        "confirmed_facts": ["平安符已出现异常"],
                        "suspected_facts": ["阿绣与旧事有关"],
                        "unrevealed_facts": [],
                        "forbidden_premature_reveals": [],
                        "protagonist_known_facts": ["平安符已出现异常"],
                        "reader_known_facts": ["平安符已出现异常"],
                        "relationship_unknowns": ["阿绣是谁"],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (root / "03_locked/state/trackers/ch01_artifact_state.json").write_text(
                json.dumps(
                    {
                        "chapter_id": "ch01",
                        "items": [
                            {"item_id": "artifact_001", "label": "平安符", "holder": "主角", "location": "袖里", "visibility": "hidden", "significance_level": "high", "last_changed_scene": "ch01_scene03", "linked_facts": ["平安符已出现异常"]}
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (root / "03_locked/state/trackers/ch01_chapter_progress.json").write_text(
                json.dumps(
                    {
                        "chapter_id": "ch01",
                        "chapter_goal": "推进平安符相关线索",
                        "protagonist_goal": "查清平安符来处",
                        "protagonist_mode": "观察/求活",
                        "investigation_stage": "被动留意",
                        "risk_level": "medium",
                        "current_relationships": [],
                        "unresolved_questions": ["阿绣是谁"],
                        "completed_scene_functions": ["ch01_scene02: 发现线索", "ch01_scene03: 过渡/氛围"],
                        "remaining_scene_functions": ["触发调查"],
                        "consecutive_transition_scene_count": 1,
                        "scene_summaries": [
                            {
                                "scene_id": "ch01_scene02",
                                "scene_function": "发现线索",
                                "new_information_items": ["确认平安符背面有名字"],
                                "protagonist_decision": "先收起，不声张",
                                "state_changes": ["investigation_stage: 未启动 -> 被动留意"],
                                "artifacts_changed": [{"label": "平安符"}],
                            },
                            {
                                "scene_id": "ch01_scene03",
                                "scene_function": "过渡/氛围",
                                "new_information_items": [],
                                "protagonist_decision": "压下追问",
                                "state_changes": [],
                                "artifacts_changed": [],
                            },
                        ],
                        "chapter_structure_summary": {
                            "first_clue_scene_id": "ch01_scene02",
                            "first_old_acquaintance_hint_scene_id": "",
                            "first_investigation_trigger_scene_id": "",
                            "first_artifact_change_scene_id": "ch01_scene02",
                            "consecutive_transition_runs": [],
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            import app.main as main_module

            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                context = compile_context({"output": {"context_file": "02_working/context/current_context.md"}})
            finally:
                main_module.ROOT = previous_root

            self.assertIn("# 当前 scene contract", context)
            self.assertIn("# planner/bootstrap agent", context)
            self.assertIn("# 世界观补全 proposal", context)
            self.assertIn("# 时间线补全 proposal", context)
            self.assertIn("# 角色补全 proposal", context)
            self.assertIn("# 章节工作大纲", context)
            self.assertIn("# 最近结构化场景摘要", context)
            self.assertIn("ch01_scene02｜发现线索", context)
            self.assertIn("# 相关 tracker 摘要", context)
            self.assertIn("平安符（持有者：主角；位置：袖里；可见性：hidden）", context)
            self.assertIn("# scene writing skill router", context)
            self.assertIn("continuity-guard｜mode=scene-canon", context)
            self.assertIn("# 默认写作 skill：continuity-guard", context)
            self.assertIn("skills/continuity-guard/SKILL.md", context)
            self.assertIn("# 少量必要 prose 参考", context)
            self.assertIn("结尾参考：他把平安符压回袖里", context)
            self.assertNotIn("开头旧稿气氛开头旧稿气氛开头旧稿气氛", context)
            self.assertTrue((root / "02_working/planning/worldview_patch.md").exists())
            self.assertTrue((root / "02_working/planning/timeline_patch.md").exists())
            self.assertTrue((root / "02_working/planning/character_patch.md").exists())
            self.assertTrue((root / "02_working/planning/bootstrap_state_machine.md").exists())
            self.assertTrue((root / "02_working/outlines/ch01_outline.md").exists())

    def test_generated_task_content_carries_structural_fields(self) -> None:
        task_text = """# task_id
scene_301

# goal
继续处理当前 scene。

# scene_purpose
让局面进入新的现实阶段。

# required_information_gain
- 确认新的风险条件。

# required_plot_progress
场景结尾前必须让阻碍升级。

# required_decision_shift
主角必须改变原先的处理方式。

# required_state_change
- 风险等级必须变化。

# avoid_motifs
- 原样重复旧物回想

# output_target
02_working/drafts/scene_301.md
"""
        reviewer_result = {
            "task_id": "scene_301",
            "summary": "需要继续推进。",
            "major_issues": ["当前推进不够。"],
            "minor_issues": [],
            "information_gain": {"has_new_information": False, "new_information_items": []},
            "plot_progress": {"has_plot_progress": False, "progress_reason": ""},
            "character_decision": {"has_decision_or_behavior_shift": False, "decision_detail": ""},
        }

        content = build_generated_task_content(task_text, reviewer_result, "02_working/drafts/scene_301.md", "rewrite")

        self.assertIn("# scene_purpose\n让局面进入新的现实阶段。", content)
        self.assertIn("# required_information_gain\n- 确认新的风险条件。", content)
        self.assertIn("# required_plot_progress\n场景结尾前必须让阻碍升级。", content)
        self.assertIn("# required_decision_shift\n主角必须改变原先的处理方式。", content)
        self.assertIn("# required_state_change\n- 风险等级必须变化。", content)
        self.assertIn("# repair_focus\nstructural_repair", content)
        self.assertIn("# avoid_motifs\n- 原样重复旧物回想", content)

    def test_choose_repair_focus_returns_structural_for_missing_structural_signals(self) -> None:
        task_text = """# task_id
scene_401

# goal
继续处理当前 scene。

# required_state_change
- 物件位置必须变化。
"""
        reviewer_result = {
            "task_id": "scene_401",
            "information_gain": {"has_new_information": False, "new_information_items": []},
            "plot_progress": {"has_plot_progress": False, "progress_reason": ""},
            "character_decision": {"has_decision_or_behavior_shift": False, "decision_detail": ""},
            "major_issues": ["scene 功能没有落地。"],
            "minor_issues": [],
        }

        focus, reasons = choose_repair_focus(task_text, reviewer_result)

        self.assertEqual(focus, "structural_repair")
        self.assertTrue(any("新信息" in item for item in reasons))
        self.assertTrue(any("required_state_change" in item for item in reasons))

    def test_generated_task_content_marks_prose_repair_for_local_language_issues(self) -> None:
        task_text = """# task_id
scene_402

# goal
修订当前 scene。

# constraints
- 保持单视角

# output_target
02_working/drafts/scene_402.md
"""
        reviewer_result = {
            "task_id": "scene_402",
            "summary": "语言略显冗长。",
            "major_issues": [],
            "minor_issues": ["第2段语言略显重复，需要压缩。"],
            "information_gain": {"has_new_information": True, "new_information_items": ["确认新线索存在。"]},
            "plot_progress": {"has_plot_progress": True, "progress_reason": "局面继续向前。"},
            "character_decision": {"has_decision_or_behavior_shift": True, "decision_detail": "主角继续原计划。"},
        }

        content = build_generated_task_content(task_text, reviewer_result, "02_working/drafts/scene_402.md", "revise")

        self.assertIn("# repair_focus\nprose_repair", content)
        self.assertIn("- 修订焦点：prose_repair", content)

    def test_generated_task_content_marks_structural_repair_and_allows_structural_changes(self) -> None:
        task_text = """# task_id
scene_403

# goal
修订当前 scene。

# scene_purpose
让 scene function 真正落地。

# output_target
02_working/drafts/scene_403.md
"""
        reviewer_result = {
            "task_id": "scene_403",
            "summary": "当前写法只是换说法重复旧内容。",
            "major_issues": ["缺少信息增量，scene 功能失效。"],
            "minor_issues": [],
            "information_gain": {"has_new_information": False, "new_information_items": []},
            "plot_progress": {"has_plot_progress": False, "progress_reason": ""},
            "character_decision": {"has_decision_or_behavior_shift": False, "decision_detail": ""},
        }

        content = build_generated_task_content(task_text, reviewer_result, "02_working/drafts/scene_403.md", "revise")

        self.assertIn("# repair_focus\nstructural_repair", content)
        self.assertIn("基于上一版草稿进行结构修复", content)
        self.assertIn("- structural_repair 允许动作：", content)
        self.assertIn("- 必须把 scene contract 缺失项补写落地，不能只做语言微修。", content)

    def test_build_validation_errors_rejects_empty_draft(self) -> None:
        task_text = """# task_id
scene_200

# goal
写一个短场景。

# constraints
- 保持单视角
"""

        errors = build_validation_errors(task_text, "   \n\n  ")

        self.assertEqual(errors, ["草稿为空，未生成有效小说正文"])

    def test_write_draft_recovers_parenthetical_only_output_via_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "prompts").mkdir(parents=True, exist_ok=True)
            (root / "01_inputs/tasks").mkdir(parents=True, exist_ok=True)
            (root / "02_working/context").mkdir(parents=True, exist_ok=True)
            (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
            (root / "02_working/reviews").mkdir(parents=True, exist_ok=True)
            (root / "00_manifest").mkdir(parents=True, exist_ok=True)

            (root / "prompts/writer_system.md").write_text("writer system", encoding="utf-8")
            (root / "prompts/output_schema.json").write_text(
                '{"type":"object","required":["task_id","goal","used_sources","risks","next_action","draft_file"],"properties":{"task_id":{"type":"string"},"goal":{"type":"string"},"used_sources":{"type":"array"},"risks":{"type":"array"},"next_action":{"type":"string"},"draft_file":{"type":"string"}}}',
                encoding="utf-8",
            )
            (root / "01_inputs/tasks/current_task.md").write_text(
                """# task_id
scene_parenthetical

# goal
写一个短场景。

# output_target
02_working/drafts/scene_parenthetical.md
""",
                encoding="utf-8",
            )
            for rel_path in [
                "00_manifest/novel_manifest.md",
                "00_manifest/world_bible.md",
                "00_manifest/character_bible.md",
                "01_inputs/life_notes/latest.md",
            ]:
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")

            import app.main as main_module

            previous_root = main_module.ROOT
            original_call_ollama = main_module.call_ollama
            original_rewrite = main_module.rewrite_script_to_prose
            main_module.ROOT = root
            try:
                main_module.call_ollama = lambda **kwargs: "（他把盐袋轻轻挪开，像临时让出半寸位置。）"
                main_module.rewrite_script_to_prose = lambda config, current_context, bad_draft: "他把盐袋轻轻挪开，像临时让出半寸位置。"

                result = write_draft(
                    {
                        "writer": {"model": "fake", "base_url": "http://example.com"},
                        "generation": {"write_num_ctx": 2048, "temperature": 0.4, "request_timeout": 10},
                        "output": {"draft_dir": "02_working/drafts", "context_file": "02_working/context/current_context.md"},
                    },
                    "上下文",
                )
            finally:
                main_module.call_ollama = original_call_ollama
                main_module.rewrite_script_to_prose = original_rewrite
                main_module.ROOT = previous_root

            saved_draft = (root / "02_working/drafts/scene_parenthetical.md").read_text(encoding="utf-8")
            self.assertEqual(result["draft_file"], "02_working/drafts/scene_parenthetical.md")
            self.assertEqual(saved_draft, "他把盐袋轻轻挪开，像临时让出半寸位置。")
            self.assertTrue((root / "02_working/logs/scene_parenthetical_first_failed_raw.md").exists())

    def test_contains_script_style_flags_single_parenthetical_block(self) -> None:
        problems = contains_script_style("（他把木箱挪开半寸，风从缝里钻了进来，煤油灯晃了一下。）")

        self.assertIn("整段文本为括号包裹的舞台说明", problems)

    def test_write_draft_recovers_truncated_output_via_continuation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "prompts").mkdir(parents=True, exist_ok=True)
            (root / "01_inputs/tasks").mkdir(parents=True, exist_ok=True)
            (root / "02_working/context").mkdir(parents=True, exist_ok=True)
            (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
            (root / "02_working/reviews").mkdir(parents=True, exist_ok=True)
            (root / "00_manifest").mkdir(parents=True, exist_ok=True)

            (root / "prompts/writer_system.md").write_text("writer system", encoding="utf-8")
            (root / "prompts/output_schema.json").write_text(
                '{"type":"object","required":["task_id","goal","used_sources","risks","next_action","draft_file"],"properties":{"task_id":{"type":"string"},"goal":{"type":"string"},"used_sources":{"type":"array"},"risks":{"type":"array"},"next_action":{"type":"string"},"draft_file":{"type":"string"}}}',
                encoding="utf-8",
            )
            (root / "01_inputs/tasks/current_task.md").write_text(
                """# task_id
scene_truncated

# goal
写一个短场景。

# output_target
02_working/drafts/scene_truncated.md
""",
                encoding="utf-8",
            )
            for rel_path in [
                "00_manifest/novel_manifest.md",
                "00_manifest/world_bible.md",
                "00_manifest/character_bible.md",
                "01_inputs/life_notes/latest.md",
            ]:
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")

            import app.main as main_module

            previous_root = main_module.ROOT
            original_call_ollama = main_module.call_ollama
            original_continue = main_module.continue_truncated_draft
            main_module.ROOT = root
            try:
                main_module.call_ollama = lambda **kwargs: "仓库角落的煤油灯突然熄灭。孟浮灯摸出火柴时，火"
                main_module.continue_truncated_draft = lambda config, current_context, bad_draft: "仓库角落的煤油灯突然熄灭。孟浮灯摸出火柴时，火苗在指间一闪，又被风压低了半寸。他护着那点亮色，把眼前的活计重新看清。"

                result = write_draft(
                    {
                        "writer": {"model": "fake", "base_url": "http://example.com"},
                        "generation": {"write_num_ctx": 2048, "temperature": 0.4, "request_timeout": 10},
                        "output": {"draft_dir": "02_working/drafts", "context_file": "02_working/context/current_context.md"},
                    },
                    "上下文",
                )
            finally:
                main_module.call_ollama = original_call_ollama
                main_module.continue_truncated_draft = original_continue
                main_module.ROOT = previous_root

            saved_draft = (root / "02_working/drafts/scene_truncated.md").read_text(encoding="utf-8")
            self.assertEqual(result["draft_file"], "02_working/drafts/scene_truncated.md")
            self.assertTrue(saved_draft.endswith("把眼前的活计重新看清。"))
            self.assertTrue((root / "02_working/logs/scene_truncated_continued_attempt.md").exists())

    def test_write_draft_repairs_validation_errors_before_failing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "prompts").mkdir(parents=True, exist_ok=True)
            (root / "01_inputs/tasks").mkdir(parents=True, exist_ok=True)
            (root / "02_working/context").mkdir(parents=True, exist_ok=True)
            (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
            (root / "02_working/reviews").mkdir(parents=True, exist_ok=True)
            (root / "00_manifest").mkdir(parents=True, exist_ok=True)

            (root / "prompts/writer_system.md").write_text("writer system", encoding="utf-8")
            (root / "prompts/output_schema.json").write_text(
                '{"type":"object","required":["task_id","goal","used_sources","risks","next_action","draft_file"],"properties":{"task_id":{"type":"string"},"goal":{"type":"string"},"used_sources":{"type":"array"},"risks":{"type":"array"},"next_action":{"type":"string"},"draft_file":{"type":"string"}}}',
                encoding="utf-8",
            )
            (root / "01_inputs/tasks/current_task.md").write_text(
                """# task_id
scene_modern

# goal
写一个短场景。

# output_target
02_working/drafts/scene_modern.md
""",
                encoding="utf-8",
            )
            for rel_path in [
                "00_manifest/novel_manifest.md",
                "00_manifest/world_bible.md",
                "00_manifest/character_bible.md",
                "01_inputs/life_notes/latest.md",
            ]:
                path = root / rel_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")

            import app.main as main_module

            previous_root = main_module.ROOT
            original_call_ollama = main_module.call_ollama
            original_repair = main_module.repair_invalid_draft
            main_module.ROOT = root
            try:
                main_module.call_ollama = lambda **kwargs: "远处传来运尸车碾过石板的闷响。"
                main_module.repair_invalid_draft = lambda config, current_context, bad_draft, errors: "远处传来板车碾过石板的闷响。"

                result = write_draft(
                    {
                        "writer": {"model": "fake", "base_url": "http://example.com"},
                        "generation": {"write_num_ctx": 2048, "temperature": 0.4, "request_timeout": 10},
                        "output": {"draft_dir": "02_working/drafts", "context_file": "02_working/context/current_context.md"},
                    },
                    "上下文",
                )
            finally:
                main_module.call_ollama = original_call_ollama
                main_module.repair_invalid_draft = original_repair
                main_module.ROOT = previous_root

            saved_draft = (root / "02_working/drafts/scene_modern.md").read_text(encoding="utf-8")
            self.assertEqual(result["draft_file"], "02_working/drafts/scene_modern.md")
            self.assertEqual(saved_draft, "远处传来板车碾过石板的闷响。")
            self.assertTrue((root / "02_working/logs/scene_modern_repaired_attempt.md").exists())

    def test_generated_followup_task_strips_accumulated_revision_pollution(self) -> None:
        task_text = """# task_id
2026-04-03-017-R5

# goal
基于上一版草稿进行小修：承接 ch01_scene09 写出 scene10。本次重点解决：旧问题A。本次重点解决：旧问题B。

# constraints
- 保持单视角
- 不新增制度性设定
- 修订模式：full_redraft
- repair_plan 执行动作：
- 旧动作一
- 旧动作二
- 额外修订要求：旧要求A
- 额外修订要求：旧要求B

# preferred_length
500-900字

# output_target
02_working/drafts/ch01_scene10_v6.md
"""

        reviewer_result = {
            "summary": "新的问题摘要。",
            "major_issues": ["新的核心问题。"],
            "minor_issues": [],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            import app.main as main_module

            previous_root = main_module.ROOT
            main_module.ROOT = Path(tmp_dir)
            try:
                content = build_generated_task_content(
                    task_text,
                    reviewer_result,
                    "02_working/drafts/ch01_scene10_v6.md",
                    "revise",
                )
            finally:
                main_module.ROOT = previous_root

        self.assertIn("承接 ch01_scene09 写出 scene10。", content)
        self.assertNotIn("旧问题A", content)
        self.assertNotIn("旧问题B", content)
        self.assertNotIn("旧动作一", content)
        self.assertNotIn("旧动作二", content)
        self.assertNotIn("旧要求A", content)
        self.assertNotIn("旧要求B", content)

    def test_build_locked_chapter_file_uses_canonical_scene_name(self) -> None:
        task_text = """# task_id
2026-04-03-018_ch01_scene11_auto-RW1-RW1

# output_target
02_working/drafts/ch01_scene11_v3_rewrite_v8_rewrite.md
"""

        locked_file = build_locked_chapter_file(
            task_text,
            "02_working/drafts/ch01_scene11_v3_rewrite_v8_rewrite.md",
            "03_locked",
        )

        self.assertEqual(locked_file, "03_locked/chapters/ch01_scene11.md")

    def test_should_continue_after_lock_honors_target_scene(self) -> None:
        config = {"generation": {"auto_continue_until_scene": 15}}

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            task_file = root / "01_inputs/tasks/generated/2026-04-03-018_ch01_scene11_auto.md"
            task_file.parent.mkdir(parents=True, exist_ok=True)
            task_file.write_text(
                """# task_id
2026-04-03-018_ch01_scene11_auto

# output_target
02_working/drafts/ch01_scene11.md
""",
                encoding="utf-8",
            )

            import app.main as main_module

            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                self.assertTrue(should_continue_after_lock(config, "01_inputs/tasks/generated/2026-04-03-018_ch01_scene11_auto.md"))
                self.assertFalse(should_continue_after_lock({"generation": {"auto_continue_until_scene": 10}}, "01_inputs/tasks/generated/2026-04-03-018_ch01_scene11_auto.md"))
            finally:
                main_module.ROOT = previous_root

    def test_supervisor_retry_budget_uses_task_metadata(self) -> None:
        task_text = """# task_id
scene_090-R5

# supervisor_round
2
"""

        self.assertEqual(extract_supervisor_round(task_text), 2)
        self.assertTrue(has_supervisor_retry_budget({"generation": {"max_supervisor_rounds": 3}}, task_text))
        self.assertFalse(has_supervisor_retry_budget({"generation": {"max_supervisor_rounds": 2}}, task_text))

    def test_prepare_supervisor_rescue_draft_saves_validated_draft(self) -> None:
        task_text = """# task_id
scene_091-RW1

# constraints
- 保持单视角

# output_target
02_working/drafts/scene_091_rewrite.md
"""
        reviewer_result = {"task_id": "scene_091-R5", "summary": "需要重写。"}

        import app.main as main_module

        previous_runner = main_module.run_supervisor_rescue_draft
        previous_root = main_module.ROOT
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            main_module.ROOT = root
            (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
            (root / "02_working/drafts/scene_091_v6.md").write_text("旧稿", encoding="utf-8")
            main_module.run_supervisor_rescue_draft = lambda *args, **kwargs: {
                "task_id": "scene_091-RW1",
                "source_draft_file": "02_working/drafts/scene_091_v6.md",
                "draft_text": "孟浮灯把木箱边渗开的水痕又擦了一遍，擦到一半，手却停住，没立刻把那点褐印彻底抹净。",
            }
            try:
                draft_file, record_file = maybe_prepare_supervisor_rescue_draft(
                    {"supervisor": {"enabled": True}, "generation": {"supervisor_rescue_draft_enabled": True}},
                    task_text,
                    "02_working/drafts/scene_091_v6.md",
                    reviewer_result,
                )
            finally:
                main_module.run_supervisor_rescue_draft = previous_runner
                main_module.ROOT = previous_root

            self.assertEqual(draft_file, "02_working/drafts/scene_091_rewrite.md")
            self.assertIsNotNone(record_file)
            self.assertTrue((root / "02_working/drafts/scene_091_rewrite.md").exists())

    def test_prepare_supervisor_rescue_draft_rejects_scene10_old_pattern_reuse(self) -> None:
        task_text = """# task_id
2026-04-03-017-RW4

# goal
重写 scene10。

# output_target
02_working/drafts/ch01_scene10_v6_rewrite4.md
"""
        reviewer_result = {"task_id": "2026-04-03-017-RW3", "summary": "需要重写。"}

        import app.main as main_module

        previous_runner = main_module.run_supervisor_rescue_draft
        previous_root = main_module.ROOT
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            main_module.ROOT = root
            (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
            (root / "02_working/drafts/ch01_scene10_v6_rewrite3.md").write_text("旧稿", encoding="utf-8")
            main_module.run_supervisor_rescue_draft = lambda *args, **kwargs: {
                "task_id": "2026-04-03-017-RW4",
                "source_draft_file": "02_working/drafts/ch01_scene10_v6_rewrite3.md",
                "draft_text": "他把多余的绳头绕上去，又留着那一截尾端在风里轻轻晃。",
            }
            try:
                draft_file, record_file = maybe_prepare_supervisor_rescue_draft(
                    {"supervisor": {"enabled": True}, "generation": {"supervisor_rescue_draft_enabled": True}},
                    task_text,
                    "02_working/drafts/ch01_scene10_v6_rewrite3.md",
                    reviewer_result,
                )
            finally:
                main_module.run_supervisor_rescue_draft = previous_runner
                main_module.ROOT = previous_root

            self.assertIsNone(draft_file)
            self.assertIsNotNone(record_file)
            self.assertFalse((root / "02_working/drafts/ch01_scene10_v6_rewrite4.md").exists())

    def test_detect_scene10_old_pattern_reuse_flags_legacy_knot_tail_moves(self) -> None:
        issues = detect_scene10_old_pattern_reuse("他把多余的绳头绕上去，没有割掉，任由那截尾端垂在那里。")

        self.assertTrue(any("改结" in item or "留线头" in item or "绳尾" in item for item in issues))


if __name__ == "__main__":
    unittest.main()
