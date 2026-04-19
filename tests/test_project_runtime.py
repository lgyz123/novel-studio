import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.chapter_orchestrator import build_chapter_opening_task, render_chapter_state, should_rollover_after_lock
import app.main as main_module
from app.project_inputs import render_human_input_markdown
from app.runtime_config import load_runtime_config


class ProjectRuntimeTest(unittest.TestCase):
    def test_render_human_input_markdown_groups_manual_fields(self) -> None:
        markdown = render_human_input_markdown(
            {
                "project": {
                    "novel_title": "九州仙途",
                    "genre": "修仙",
                    "premise": "采药少年误入仙途。",
                },
                "cast": {
                    "protagonist": {
                        "name": "楚天阳",
                        "description": "出身低微的采药少年。",
                    }
                },
                "story_blueprint": {
                    "chapter_goal": "先立主角求活处境，再给出异变入口。",
                },
                "manual_required": {
                    "must_have": ["开篇即给出核心奇遇"],
                    "must_avoid": ["不要现代口语"],
                },
            }
        )

        self.assertIn("# Human Input", markdown)
        self.assertIn("小说名：九州仙途", markdown)
        self.assertIn("姓名：楚天阳", markdown)
        self.assertIn("## 故事蓝图", markdown)
        self.assertIn("## 必须出现", markdown)
        self.assertIn("## 必须避免", markdown)

    def test_load_runtime_config_merges_run_config_over_base_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "app").mkdir(parents=True, exist_ok=True)
            (root / "01_inputs").mkdir(parents=True, exist_ok=True)
            (root / "app/config.yaml").write_text(
                "generation:\n  max_auto_revisions: 5\nrun:\n  mode: continue\n  target_chapter: 1\n",
                encoding="utf-8",
            )
            (root / "01_inputs/run_config.yaml").write_text(
                "run:\n  mode: restart\n  target_chapter: 3\n  restart_from_task: 01_inputs/tasks/start.md\n",
                encoding="utf-8",
            )

            config = load_runtime_config(root)

        self.assertEqual(config["run"]["mode"], "restart")
        self.assertEqual(config["run"]["target_chapter"], 3)
        self.assertEqual(config["generation"]["max_auto_revisions"], 5)

    def test_save_latest_run_summary_includes_trace_and_created_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                rel_path = main_module.save_latest_run_summary(
                    task_id="scene_summary",
                    draft_file="02_working/drafts/scene_summary.md",
                    writer_trace={
                        "provider": "ollama",
                        "mode": "draft_generated",
                        "fallbacks_used": ["rewrite_script_to_prose"],
                        "initial_validation_errors": ["文本呈现提纲/列表式格式，不符合小说正文要求"],
                        "final_validation_errors": [],
                    },
                    reviewer_result={
                        "verdict": "revise",
                        "summary": "需要小修。",
                        "major_issues": ["动作推进不足。"],
                        "minor_issues": ["结尾收束偏弱。"],
                        "review_trace": {
                            "provider": "ollama",
                            "mode": "deterministic_fallback",
                            "json_refinement_attempted": False,
                            "deterministic_fallback_used": True,
                            "low_confidence": True,
                            "repeated_fragments": 4,
                        },
                    },
                    created={
                        "task_file": "01_inputs/tasks/generated/scene_summary_revision_auto.md",
                        "supervisor_decision_file": "02_working/reviews/scene_summary_supervisor_decision.json",
                    },
                    loop_round=2,
                    review_status="revise",
                )
                content = (root / rel_path).read_text(encoding="utf-8")
            finally:
                main_module.ROOT = previous_root

        self.assertEqual(rel_path, "02_working/reviews/latest_run_summary.md")
        self.assertIn("task_id: scene_summary", content)
        self.assertIn("## Writer Trace", content)
        self.assertIn("rewrite_script_to_prose", content)
        self.assertIn("mode: deterministic_fallback", content)
        self.assertIn("task_file: 01_inputs/tasks/generated/scene_summary_revision_auto.md", content)
        self.assertIn("supervisor_decision_file", content)

    def test_summary_helper_tolerates_supervisor_decision_without_rescue_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                rel_path = main_module.save_latest_run_summary(
                    task_id="scene_supervisor_only",
                    draft_file="02_working/drafts/scene_supervisor_only.md",
                    writer_trace={},
                    reviewer_result={
                        "verdict": "revise",
                        "summary": "supervisor 已接管。",
                        "major_issues": ["需要继续修订。"],
                        "minor_issues": [],
                    },
                    created={
                        "supervisor_decision_file": "02_working/reviews/scene_supervisor_only_supervisor_decision.json",
                        "task_file": "01_inputs/tasks/generated/scene_supervisor_only_revision_auto.md",
                    },
                    loop_round=1,
                    review_status="revise",
                )
                content = (root / rel_path).read_text(encoding="utf-8")
            finally:
                main_module.ROOT = previous_root

        self.assertIn("scene_supervisor_only_supervisor_decision.json", content)
        self.assertNotIn("supervisor_rescue_record_file", content)

    def test_should_continue_after_lock_respects_target_chapter_and_scene(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                task_file = root / "01_inputs/tasks/generated/ch02_scene03.md"
                task_file.parent.mkdir(parents=True, exist_ok=True)
                task_file.write_text("# output_target\n02_working/drafts/ch02_scene03.md\n", encoding="utf-8")

                self.assertTrue(
                    main_module.should_continue_after_lock(
                        {"run": {"target_chapter": 2}},
                        "01_inputs/tasks/generated/ch02_scene03.md",
                    )
                )
                self.assertFalse(
                    main_module.should_continue_after_lock(
                        {"run": {"target_chapter": 1}},
                        "01_inputs/tasks/generated/ch02_scene03.md",
                    )
                )
                self.assertFalse(
                    main_module.should_continue_after_lock(
                        {"run": {"target_chapter": 2, "target_scene": 2}},
                        "01_inputs/tasks/generated/ch02_scene03.md",
                    )
                )
            finally:
                main_module.ROOT = previous_root

    def test_restart_mode_skips_existing_draft_reuse_for_all_rounds(self) -> None:
        self.assertTrue(main_module.should_skip_existing_draft_reuse({"run": {"mode": "restart"}}, 1))
        self.assertTrue(main_module.should_skip_existing_draft_reuse({"run": {"mode": "restart"}}, 3))
        self.assertFalse(main_module.should_skip_existing_draft_reuse({"run": {"mode": "continue"}}, 3))

    def test_prepare_runtime_start_overwrites_current_task_in_restart_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                (root / "01_inputs/tasks").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs/tasks/start.md").write_text(
                    "# task_id\n2026-04-15-001_ch01_scene01_auto\n",
                    encoding="utf-8",
                )
                (root / "01_inputs/tasks/current_task.md").write_text(
                    "# task_id\nold_task\n",
                    encoding="utf-8",
                )

                task_id = main_module.prepare_runtime_start(
                    {"run": {"mode": "restart", "restart_from_task": "01_inputs/tasks/start.md"}}
                )

                current_task = (root / "01_inputs/tasks/current_task.md").read_text(encoding="utf-8")
            finally:
                main_module.ROOT = previous_root

        self.assertEqual(task_id, "2026-04-15-001_ch01_scene01_auto")
        self.assertIn("2026-04-15-001_ch01_scene01_auto", current_task)

    def test_prepare_runtime_start_can_bootstrap_from_start_chapter_without_task_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                (root / "00_manifest").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs/tasks").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs").mkdir(parents=True, exist_ok=True)
                (root / "00_manifest/novel_manifest.md").write_text(
                    "#### 第一卷：灰灯卷\n- 功能：从运河捞尸切入，建立底层视角与仙门录名黑幕\n",
                    encoding="utf-8",
                )
                (root / "01_inputs/human_input.yaml").write_text(
                    "protagonist:\n  name: 楚天阳\n",
                    encoding="utf-8",
                )

                task_id = main_module.prepare_runtime_start(
                    {"run": {"mode": "restart", "start_chapter": 2, "start_scene": 1}, "generation": {}}
                )

                current_task = (root / "01_inputs/tasks/current_task.md").read_text(encoding="utf-8")
            finally:
                main_module.ROOT = previous_root

        self.assertIn("_ch02_scene01_auto", task_id or "")
        self.assertIn("# chapter_state\n03_locked/canon/ch02_state.md", current_task)

    def test_prepare_runtime_start_in_continue_mode_advances_from_already_locked_scene(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                (root / "00_manifest").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs/tasks/generated").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs").mkdir(parents=True, exist_ok=True)
                (root / "00_manifest/novel_manifest.md").write_text(
                    "#### 第一卷：灰灯卷\n- 功能：从运河捞尸切入，建立底层视角与仙门录名黑幕\n",
                    encoding="utf-8",
                )
                (root / "01_inputs/human_input.yaml").write_text(
                    "project:\n  premise: 采药少年误入仙途。\n  genre: 修仙\ncast:\n  protagonist:\n    name: 楚天阳\n",
                    encoding="utf-8",
                )
                (root / "03_locked/chapters/ch02_scene02.md").write_text("已锁正文", encoding="utf-8")
                (root / "01_inputs/tasks/current_task.md").write_text(
                    "# task_id\n2026-04-16-028_ch02_scene02_auto\n\n# output_target\n02_working/drafts/ch02_scene02.md\n",
                    encoding="utf-8",
                )

                task_id = main_module.prepare_runtime_start(
                    {
                        "run": {"mode": "continue", "target_chapter": 2, "target_scene": 3},
                        "generation": {},
                        "paths": {"locked_dir": "03_locked"},
                    }
                )

                current_task = (root / "01_inputs/tasks/current_task.md").read_text(encoding="utf-8")
            finally:
                main_module.ROOT = previous_root

        self.assertIn("_ch02_scene03_auto", task_id or "")
        self.assertIn("# output_target\n02_working/drafts/ch02_scene03.md", current_task)

    def test_prepare_runtime_start_in_continue_mode_maps_revision_output_to_locked_scene(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                (root / "00_manifest").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs/tasks/generated").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs").mkdir(parents=True, exist_ok=True)
                (root / "00_manifest/novel_manifest.md").write_text(
                    "#### 第一卷：灰灯卷\n- 功能：从运河捞尸切入，建立底层视角与仙门录名黑幕\n",
                    encoding="utf-8",
                )
                (root / "01_inputs/human_input.yaml").write_text(
                    "project:\n  premise: 采药少年误入仙途。\n  genre: 修仙\ncast:\n  protagonist:\n    name: 楚天阳\n",
                    encoding="utf-8",
                )
                (root / "03_locked/chapters/ch02_scene02.md").write_text("已锁正文", encoding="utf-8")
                (root / "01_inputs/tasks/current_task.md").write_text(
                    "# task_id\n2026-04-16-028_ch02_scene02_auto-R2\n\n# output_target\n02_working/drafts/ch02_scene02_v3.md\n",
                    encoding="utf-8",
                )

                task_id = main_module.prepare_runtime_start(
                    {
                        "run": {"mode": "continue", "target_chapter": 2, "target_scene": 3},
                        "generation": {},
                        "paths": {"locked_dir": "03_locked"},
                    }
                )

                current_task = (root / "01_inputs/tasks/current_task.md").read_text(encoding="utf-8")
            finally:
                main_module.ROOT = previous_root

        self.assertIn("_ch02_scene03_auto", task_id or "")
        self.assertIn("# output_target\n02_working/drafts/ch02_scene03.md", current_task)

    def test_prepare_runtime_start_in_continue_mode_prefers_latest_locked_over_stale_revision_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                (root / "00_manifest").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs/tasks/generated").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs").mkdir(parents=True, exist_ok=True)
                (root / "00_manifest/novel_manifest.md").write_text(
                    "#### 第一卷：灰灯卷\n- 功能：从运河捞尸切入，建立底层视角与仙门录名黑幕\n",
                    encoding="utf-8",
                )
                (root / "01_inputs/human_input.yaml").write_text(
                    "project:\n  premise: 采药少年误入仙途。\n  genre: 修仙\ncast:\n  protagonist:\n    name: 楚天阳\n",
                    encoding="utf-8",
                )
                (root / "03_locked/chapters/ch01_scene08.md").write_text("已锁正文", encoding="utf-8")
                (root / "01_inputs/tasks/current_task.md").write_text(
                    "# task_id\n2026-04-18-017_ch01_scene07_auto-R4\n\n# output_target\n02_working/drafts/ch01_scene07_v5.md\n",
                    encoding="utf-8",
                )

                task_id = main_module.prepare_runtime_start(
                    {
                        "run": {"mode": "continue", "target_chapter": 1, "target_scene": 10},
                        "generation": {},
                        "paths": {"locked_dir": "03_locked"},
                    }
                )

                current_task = (root / "01_inputs/tasks/current_task.md").read_text(encoding="utf-8")
            finally:
                main_module.ROOT = previous_root

        self.assertIn("_ch01_scene09_auto", task_id or "")
        self.assertIn("# output_target\n02_working/drafts/ch01_scene09.md", current_task)

    def test_prepare_runtime_start_in_continue_mode_can_resume_from_latest_summary_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                (root / "00_manifest").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs/tasks/generated").mkdir(parents=True, exist_ok=True)
                (root / "02_working/reviews").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs").mkdir(parents=True, exist_ok=True)
                (root / "00_manifest/novel_manifest.md").write_text(
                    "#### 第一卷：灰灯卷\n- 功能：从运河捞尸切入，建立底层视角与仙门录名黑幕\n",
                    encoding="utf-8",
                )
                (root / "01_inputs/human_input.yaml").write_text(
                    "project:\n  premise: 采药少年误入仙途。\n  genre: 修仙\ncast:\n  protagonist:\n    name: 楚天阳\n",
                    encoding="utf-8",
                )
                (root / "03_locked/chapters/ch01_scene04.md").write_text("已锁正文", encoding="utf-8")
                (root / "01_inputs/tasks/generated/2026-04-19-013_ch01_scene06_auto-R1.md").write_text(
                    "# task_id\n2026-04-19-013_ch01_scene06_auto-R1\n\n# output_target\n02_working/drafts/ch01_scene06_v2.md\n",
                    encoding="utf-8",
                )
                (root / "02_working/reviews/latest_run_summary.md").write_text(
                    "# Latest Run Summary\n\n## 本轮概况\n- task_id: 2026-04-19-013_ch01_scene06_auto-R1\n- review_status: revise\n\n## 输出产物\n- task_file: 01_inputs/tasks/generated/2026-04-19-013_ch01_scene06_auto-R1.md\n",
                    encoding="utf-8",
                )

                task_id = main_module.prepare_runtime_start(
                    {
                        "run": {"mode": "continue", "target_chapter": 1, "target_scene": 10},
                        "generation": {},
                        "paths": {"locked_dir": "03_locked"},
                    }
                )

                current_task = (root / "01_inputs/tasks/current_task.md").read_text(encoding="utf-8")
            finally:
                main_module.ROOT = previous_root

        self.assertEqual(task_id, "2026-04-19-013_ch01_scene06_auto-R1")
        self.assertIn("# output_target\n02_working/drafts/ch01_scene06_v2.md", current_task)

    def test_prepare_runtime_start_in_continue_mode_ignores_locked_summary_task_and_advances(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                (root / "00_manifest").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs/tasks/generated").mkdir(parents=True, exist_ok=True)
                (root / "02_working/reviews").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs").mkdir(parents=True, exist_ok=True)
                (root / "00_manifest/novel_manifest.md").write_text(
                    "#### 第一卷：灰灯卷\n- 功能：从运河捞尸切入，建立底层视角与仙门录名黑幕\n",
                    encoding="utf-8",
                )
                (root / "01_inputs/human_input.yaml").write_text(
                    "project:\n  premise: 采药少年误入仙途。\n  genre: 修仙\ncast:\n  protagonist:\n    name: 楚天阳\n",
                    encoding="utf-8",
                )
                (root / "03_locked/chapters/ch01_scene06.md").write_text("已锁正文", encoding="utf-8")
                (root / "01_inputs/tasks/generated/2026-04-19-013_ch01_scene06_auto.md").write_text(
                    "# task_id\n2026-04-19-013_ch01_scene06_auto\n\n# output_target\n02_working/drafts/ch01_scene06.md\n",
                    encoding="utf-8",
                )
                (root / "02_working/reviews/latest_run_summary.md").write_text(
                    "# Latest Run Summary\n\n## 本轮概况\n- task_id: 2026-04-19-013_ch01_scene06_auto\n- review_status: lock\n\n## 输出产物\n- task_file: 01_inputs/tasks/generated/2026-04-19-013_ch01_scene06_auto.md\n- locked_file: 03_locked/chapters/ch01_scene06.md\n",
                    encoding="utf-8",
                )

                task_id = main_module.prepare_runtime_start(
                    {
                        "run": {"mode": "continue", "target_chapter": 1, "target_scene": 7},
                        "generation": {},
                        "paths": {"locked_dir": "03_locked"},
                    }
                )

                current_task = (root / "01_inputs/tasks/current_task.md").read_text(encoding="utf-8")
            finally:
                main_module.ROOT = previous_root

        self.assertIn("_ch01_scene07_auto", task_id or "")
        self.assertIn("# output_target\n02_working/drafts/ch01_scene07.md", current_task)

    def test_build_chapter_opening_task_uses_human_input_and_previous_locked_scene(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "00_manifest").mkdir(parents=True, exist_ok=True)
            (root / "01_inputs").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
            (root / "00_manifest/novel_manifest.md").write_text(
                "#### 第一卷：灰灯卷\n- 功能：从运河捞尸切入，建立底层视角与仙门录名黑幕\n",
                encoding="utf-8",
            )
            (root / "01_inputs/human_input.yaml").write_text(
                "project:\n  premise: 采药少年误入仙途。\n  genre: 修仙\ncast:\n  protagonist:\n    name: 楚天阳\nstory_blueprint:\n  chapter_goal: 先立足，再触发异变。\n",
                encoding="utf-8",
            )
            (root / "03_locked/chapters/ch01_scene12.md").write_text("上一章结尾", encoding="utf-8")

            task_id, task_text = build_chapter_opening_task(
                root,
                {"generation": {"preferred_length_override": "2000-3000字"}},
                chapter_number=2,
                previous_locked_file="03_locked/chapters/ch01_scene12.md",
            )

        self.assertIn("_ch02_scene01_auto", task_id)
        self.assertIn("楚天阳", task_text)
        self.assertIn("03_locked/chapters/ch01_scene12.md", task_text)
        self.assertIn("# chapter_state\n03_locked/canon/ch02_state.md", task_text)
        self.assertIn("# output_target\n02_working/drafts/ch02_scene01.md", task_text)
        self.assertIn("当前章节目标", task_text)

    def test_render_chapter_state_includes_chapter_spine_and_existing_locked_scene(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "00_manifest").mkdir(parents=True, exist_ok=True)
            (root / "01_inputs").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
            (root / "00_manifest/novel_manifest.md").write_text(
                "#### 第一卷：灰灯卷\n- 功能：从运河捞尸切入，建立底层视角与仙门录名黑幕\n",
                encoding="utf-8",
            )
            (root / "01_inputs/human_input.yaml").write_text(
                "project:\n  premise: 采药少年误入仙途。\nstory_blueprint:\n  chapter_goal: 第一章先立足，再给出新的现实压力。\nmanual_required:\n  must_have:\n    - 让主角先感到新的催逼。\n  open_questions:\n    - 名字背后的来历先不揭破。\ncast:\n  protagonist:\n    name: 楚天阳\n",
                encoding="utf-8",
            )
            (root / "03_locked/chapters/ch01_scene01.md").write_text("已锁正文", encoding="utf-8")
            (root / "03_locked/state/story_state.json").write_text(
                "{\n  \"characters\": {\"protagonist\": {\"known_facts\": [\"半截红绳\"], \"active_goals\": [\"先把眼前麻烦压下去\"]}},\n  \"items\": [{\"name\": \"平安符\"}]\n}",
                encoding="utf-8",
            )

            chapter_state = render_chapter_state(root, 1)

        self.assertIn("## 本章主线骨架", chapter_state)
        self.assertIn("本章目标", chapter_state)
        self.assertIn("新压力源", chapter_state)
        self.assertIn("错误判断", chapter_state)
        self.assertIn("03_locked/chapters/ch01_scene01.md", chapter_state)
        self.assertIn("## 当前关键物件", chapter_state)
        self.assertIn("平安符", chapter_state)

    def test_prepare_runtime_start_restart_cleans_previous_runtime_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            previous_root = main_module.ROOT
            main_module.ROOT = root
            try:
                (root / "00_manifest").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs/tasks/generated").mkdir(parents=True, exist_ok=True)
                (root / "01_inputs").mkdir(parents=True, exist_ok=True)
                (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
                (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
                (root / "00_manifest/novel_manifest.md").write_text(
                    "#### 第一卷：灰灯卷\n- 功能：从运河捞尸切入，建立底层视角与仙门录名黑幕\n",
                    encoding="utf-8",
                )
                (root / "01_inputs/human_input.yaml").write_text(
                    "project:\n  premise: 采药少年误入仙途。\ncast:\n  protagonist:\n    name: 楚天阳\n",
                    encoding="utf-8",
                )
                (root / "01_inputs/tasks/current_task.md").write_text("# task_id\nold_task\n", encoding="utf-8")
                (root / "01_inputs/tasks/generated/old.md").write_text("old", encoding="utf-8")
                (root / "02_working/drafts/old.md").write_text("old", encoding="utf-8")
                (root / "03_locked/chapters/ch01_scene01.md").write_text("old", encoding="utf-8")
                (root / "03_locked/state/story_state.json").write_text("{}", encoding="utf-8")

                task_id = main_module.prepare_runtime_start(
                    {"run": {"mode": "restart", "start_chapter": 1, "start_scene": 1}, "generation": {}}
                )
                current_task_exists = (root / "01_inputs/tasks/current_task.md").exists()
                old_draft_exists = (root / "02_working/drafts/old.md").exists()
                old_locked_exists = (root / "03_locked/chapters/ch01_scene01.md").exists()
                story_state_exists = (root / "03_locked/state/story_state.json").exists()
            finally:
                main_module.ROOT = previous_root

        self.assertIn("_ch01_scene01_auto", task_id or "")
        self.assertFalse(old_draft_exists)
        self.assertFalse(old_locked_exists)
        self.assertFalse(story_state_exists)
        self.assertTrue(current_task_exists)

    def test_should_rollover_after_lock_uses_run_scene_limit(self) -> None:
        self.assertTrue(should_rollover_after_lock({"run": {"max_scenes_per_chapter": 12}}, "03_locked/chapters/ch01_scene12.md"))
        self.assertFalse(should_rollover_after_lock({"run": {"max_scenes_per_chapter": 12}}, "03_locked/chapters/ch01_scene11.md"))


if __name__ == "__main__":
    unittest.main()
