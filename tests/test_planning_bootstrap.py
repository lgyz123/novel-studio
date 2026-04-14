import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.planning_bootstrap import infer_chapter_id, run_planning_bootstrap


class PlanningBootstrapTest(unittest.TestCase):
    def test_infer_chapter_id_prefers_task_and_falls_back_to_default(self) -> None:
        self.assertEqual(infer_chapter_id("# task_id\n2026-04-14-001_ch03_scene01_auto\n"), "ch03")
        self.assertEqual(infer_chapter_id("# task_id\nscene_auto\n", output_target="02_working/drafts/ch05_scene02.md"), "ch05")
        self.assertEqual(infer_chapter_id("# task_id\nscene_auto\n"), "ch01")

    def test_run_planning_bootstrap_writes_expected_artifacts(self) -> None:
        task_text = """# task_id
2026-04-14-001_ch01_scene01_auto

# goal
承接章节开场，继续写第一章。

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/ch01_scene01.md
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "00_manifest").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)

            (root / "00_manifest/novel_manifest.md").write_text(
                "# 总纲\n\n## 分卷安排\n- 第一卷：灰灯卷\n",
                encoding="utf-8",
            )
            (root / "00_manifest/world_bible.md").write_text(
                "# 世界观\n\n## 修行逻辑\n- 命、愿、债\n\n## 社会结构\n- 王朝\n- 宗门\n",
                encoding="utf-8",
            )
            (root / "00_manifest/character_bible.md").write_text(
                "# 人物设定\n\n### 孟浮灯\n- 捞尸为生。\n",
                encoding="utf-8",
            )
            (root / "03_locked/canon/ch01_state.md").write_text(
                "# ch01 当前状态\n\n## 已锁定场景\n- ch01_scene01：夜里回屋\n",
                encoding="utf-8",
            )
            (root / "03_locked/state/story_state.json").write_text(
                json.dumps(
                    {
                        "timeline": {
                            "current_book_time": "夜里",
                            "recent_events": ["EVENT-001", "EVENT-002"],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            outputs = run_planning_bootstrap(root, task_text, chapter_state_text=(root / "03_locked/canon/ch01_state.md").read_text(encoding="utf-8"))

            self.assertEqual(outputs["worldview_patch_file"], "02_working/planning/worldview_patch.md")
            self.assertEqual(outputs["timeline_patch_file"], "02_working/planning/timeline_patch.md")
            self.assertEqual(outputs["outline_file"], "02_working/outlines/ch01_outline.md")

            worldview = (root / outputs["worldview_patch_file"]).read_text(encoding="utf-8")
            timeline = (root / outputs["timeline_patch_file"]).read_text(encoding="utf-8")
            character = (root / outputs["character_patch_file"]).read_text(encoding="utf-8")
            outline = (root / outputs["outline_file"]).read_text(encoding="utf-8")
            state_machine = (root / outputs["state_machine_file"]).read_text(encoding="utf-8")

            self.assertIn("# 世界观补全 proposal", worldview)
            self.assertIn("## 建议补丁", worldview)
            self.assertIn("## 使用中的 skill：worldbuilding", worldview)
            self.assertIn("skills/worldbuilding/SKILL.md", worldview)
            self.assertIn("# 时间线补全 proposal", timeline)
            self.assertIn("current_book_time：夜里", timeline)
            self.assertIn("# 角色补全 proposal", character)
            self.assertIn("孟浮灯", character)
            self.assertIn("# ch01_outline 工作稿", outline)
            self.assertIn("## 与前置状态机的连接", outline)
            self.assertIn("## 使用中的 skill：scene-outline", outline)
            self.assertIn("skills/scene-outline/SKILL.md", outline)
            self.assertIn("# 前置状态机", state_machine)
            self.assertIn("角色创建", state_machine)
            self.assertIn("大纲定制", state_machine)
            self.assertIn("第一章撰写", state_machine)
            self.assertIn("## planning skill router", state_machine)
            self.assertIn("worldbuilding｜mode=institutional", state_machine)
            self.assertIn("scene-outline｜mode=chapter-outline", state_machine)


if __name__ == "__main__":
    unittest.main()
