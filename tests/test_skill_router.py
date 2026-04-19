import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.skill_router import render_skill_router_markdown, route_writer_skills


class SkillRouterTest(unittest.TestCase):
    def test_planning_bootstrap_routes_worldbuilding_and_scene_outline(self) -> None:
        result = route_writer_skills(
            phase="planning_bootstrap",
            task_text="# goal\n补全世界观并生成章节大纲\n",
            project_manifest_text="玄幻 仙侠 宗门 修行",
            state_signals={},
        )

        selected = [item["skill"] for item in result["selected_skills"]]
        self.assertEqual(selected, ["worldbuilding", "scene-outline"])
        self.assertIn("xianxia", result["genre_tags"])

    def test_scene_writing_routes_continuity_guard(self) -> None:
        result = route_writer_skills(
            phase="scene_writing",
            task_text="# chapter_state\n03_locked/canon/ch01_state.md\n# goal\n继续写 scene\n",
            project_manifest_text="玄幻 仙侠",
            state_signals={"has_story_state": True},
        )

        self.assertEqual(result["selected_skills"][0]["skill"], "continuity-guard")
        self.assertEqual(result["selected_skills"][0]["mode"], "scene-canon")
        markdown = render_skill_router_markdown(result, heading="# router")
        self.assertIn("# router", markdown)
        self.assertIn("continuity-guard", markdown)
        self.assertIn("scene_writing", markdown)

    def test_scene_writing_can_add_character_and_naming_skills(self) -> None:
        result = route_writer_skills(
            phase="scene_writing",
            task_text="# goal\n补人物设定并给人物取名。\n# chapter_state\n03_locked/canon/ch01_state.md\n",
            project_manifest_text="玄幻 仙侠",
            state_signals={"has_story_state": True},
        )

        selected = [item["skill"] for item in result["selected_skills"]]
        self.assertEqual(selected, ["continuity-guard", "character-design", "naming"])

    def test_character_creation_routes_character_design_and_naming(self) -> None:
        result = route_writer_skills(
            phase="character_creation",
            task_text="# goal\n创建主角与配角角色卡\n",
            project_manifest_text="玄幻 仙侠",
            state_signals={},
        )

        selected = [item["skill"] for item in result["selected_skills"]]
        self.assertEqual(selected, ["character-design", "naming"])

    def test_timeline_bootstrap_routes_timeline_history(self) -> None:
        result = route_writer_skills(
            phase="timeline_bootstrap",
            task_text="# goal\n补全本章时间线与历史锚点\n",
            project_manifest_text="玄幻 仙侠",
            state_signals={},
        )

        selected = [item["skill"] for item in result["selected_skills"]]
        self.assertEqual(selected, ["timeline-history"])


if __name__ == "__main__":
    unittest.main()
