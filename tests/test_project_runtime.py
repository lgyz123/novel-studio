import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.chapter_orchestrator import build_chapter_opening_task, should_rollover_after_lock
import app.main as main_module
from app.project_inputs import render_human_input_markdown
from app.runtime_config import load_runtime_config


class ProjectRuntimeTest(unittest.TestCase):
    def test_render_human_input_markdown_groups_manual_fields(self) -> None:
        markdown = render_human_input_markdown(
            {
                "basic": {
                    "novel_title": "九州仙途",
                    "genre": "修仙",
                    "premise": "采药少年误入仙途。",
                },
                "protagonist": {
                    "name": "楚天阳",
                    "description": "出身低微的采药少年。",
                },
                "must_have": ["开篇即给出核心奇遇"],
                "must_avoid": ["不要现代口语"],
            }
        )

        self.assertIn("# Human Input", markdown)
        self.assertIn("小说名：九州仙途", markdown)
        self.assertIn("姓名：楚天阳", markdown)
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
                "basic:\n  premise: 采药少年误入仙途。\n  genre: 修仙\nprotagonist:\n  name: 楚天阳\n",
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

    def test_should_rollover_after_lock_uses_run_scene_limit(self) -> None:
        self.assertTrue(should_rollover_after_lock({"run": {"max_scenes_per_chapter": 12}}, "03_locked/chapters/ch01_scene12.md"))
        self.assertFalse(should_rollover_after_lock({"run": {"max_scenes_per_chapter": 12}}, "03_locked/chapters/ch01_scene11.md"))


if __name__ == "__main__":
    unittest.main()
