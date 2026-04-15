import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from app.review_scene import audit_scene_writing_skill_router


class SkillAuditTest(unittest.TestCase):
    def test_audit_prefers_skill_audit_output_when_present(self) -> None:
        task_text = """# task_id
scene_899

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/ch01_scene01.md
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            planning_dir = root / "02_working/planning"
            planning_dir.mkdir(parents=True, exist_ok=True)
            (planning_dir / "skill_audit.json").write_text(
                json.dumps(
                    {
                        "audits": [
                            {
                                "phase": "scene_writing",
                                "selected_skills": ["continuity-guard"],
                                "major_issues": [],
                                "minor_issues": ["scene_writing router 当前启用：continuity-guard。"],
                                "is_ok": True,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (planning_dir / "scene_writing_skill_router.json").write_text(
                json.dumps(
                    {
                        "phase": "scene_writing",
                        "selected_skills": [
                            {"skill": "character-design"},
                            {"skill": "naming"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            major, minor = audit_scene_writing_skill_router(root, task_text)

            self.assertEqual(major, [])
            self.assertEqual(minor, ["[skill audit][scene_writing] scene_writing router 当前启用：continuity-guard。"])

    def test_audit_flags_missing_continuity_guard_when_chapter_state_exists(self) -> None:
        task_text = """# task_id
scene_900

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/ch01_scene01.md
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            planning_dir = root / "02_working/planning"
            planning_dir.mkdir(parents=True, exist_ok=True)
            (planning_dir / "scene_writing_skill_router.json").write_text(
                json.dumps(
                    {
                        "phase": "scene_writing",
                        "selected_skills": [
                            {"skill": "character-design"},
                            {"skill": "naming"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            major, minor = audit_scene_writing_skill_router(root, task_text)

            self.assertTrue(any("continuity-guard" in item for item in major))
            self.assertEqual(minor, [])

    def test_audit_flags_overloaded_skill_selection(self) -> None:
        task_text = """# task_id
scene_901

# output_target
02_working/drafts/ch01_scene01.md
"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            planning_dir = root / "02_working/planning"
            planning_dir.mkdir(parents=True, exist_ok=True)
            (planning_dir / "scene_writing_skill_router.json").write_text(
                json.dumps(
                    {
                        "phase": "scene_writing",
                        "selected_skills": [
                            {"skill": "continuity-guard"},
                            {"skill": "character-design"},
                            {"skill": "naming"},
                            {"skill": "timeline-history"},
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            major, _ = audit_scene_writing_skill_router(root, task_text)

            self.assertTrue(any("超过当前约定上限 3 个" in item for item in major))


if __name__ == "__main__":
    unittest.main()
