import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.prewrite_checks import build_prewrite_review, render_prewrite_review_markdown, review_timeline, review_world_bible


class PrewriteChecksTest(unittest.TestCase):
    def test_review_world_bible_flags_missing_history_dimension(self) -> None:
        world_text = """# 世界观

## 修行逻辑
- 围绕命、愿、债展开

## 社会结构
- 王朝
- 宗门
"""
        manifest_text = """# 总纲

## 核心主题
- 反对内卷
"""

        result = review_world_bible(world_text, manifest_text)

        self.assertIn("历史与变迁", result["missing_dimensions"])
        self.assertTrue(any("力量体系" in item or "关键历史事件" in item for item in result["inferred_completions"]))

    def test_review_timeline_uses_story_state_events(self) -> None:
        manifest_text = """# 总纲

## 分卷安排
- 第一卷：灰灯卷
- 第二卷：山门卷
"""
        story_state = {
            "timeline": {
                "current_book_time": "傍晚",
                "recent_events": ["EVENT-009", "EVENT-010"],
            }
        }

        result = review_timeline(manifest_text, chapter_state_text="", story_state=story_state)

        self.assertEqual(result["current_book_time"], "傍晚")
        self.assertEqual(result["recent_events"], ["EVENT-009", "EVENT-010"])
        self.assertIn("历史事件锚点", result["missing_dimensions"])

    def test_build_prewrite_review_reads_project_files_and_renders_markdown(self) -> None:
        task_text = """# task_id
2026-04-13-001_ch01_scene01_auto
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "00_manifest").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
            (root / "00_manifest/novel_manifest.md").write_text(
                "# 总纲\n\n## 分卷安排\n- 第一卷：灰灯卷\n- 第二卷：山门卷\n",
                encoding="utf-8",
            )
            (root / "00_manifest/world_bible.md").write_text(
                "# 世界观\n\n## 修行逻辑\n- 命、愿、债\n\n## 社会结构\n- 王朝\n- 宗门\n",
                encoding="utf-8",
            )
            (root / "03_locked/state/story_state.json").write_text(
                '{"timeline": {"current_book_time": "夜里", "recent_events": ["EVENT-001"]}}',
                encoding="utf-8",
            )

            review = build_prewrite_review(root, task_text, chapter_state_text="## 已锁定场景\n- scene01：夜里回屋\n")
            markdown = render_prewrite_review_markdown(review)

        self.assertEqual(review["task_id"], "2026-04-13-001_ch01_scene01_auto")
        self.assertIn("【世界观构建】 已启动", markdown)
        self.assertIn("【时间线校验】 已启动", markdown)
        self.assertIn("当前 book time：夜里", markdown)


if __name__ == "__main__":
    unittest.main()
