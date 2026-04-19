import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.story_state import STORY_STATE_REL_PATH, StoryState, clean_story_state, extract_item_candidates, load_story_state, update_story_state_on_lock
from app.story_state import rebuild_story_state_from_locked


TASK_TEXT = """# task_id
2026-04-03-016

# goal
承接上一场，继续保持码头求活与低烈度推进。

# chapter_state
03_locked/canon/ch01_state.md
"""

CHAPTER_STATE_TEXT = """# ch01 当前状态

## 已锁定场景
- scene06：次日码头做活时，“阿绣”这个名字第一次轻微影响了孟浮灯的现实动作，但仍未发展成明确调查

## 当前主角状态
- 孟浮灯仍处于底层求活状态
- 他现在不仅会被这条线轻微带偏动作，也会在做活时下意识留下本可立刻丢开的细小之物，但这种保留仍停留在极轻程度
- 他尚未形成明确调查行动，但已经无法把这个名字当作普通死者名讳轻易放下

## 已锁定线索
- 红绳
- 平安符背面的“阿绣”
- scene09 中，孟浮灯又把一截本可顺手丢掉的线头留了下来，说明“阿绣”这条线已开始牵动他对细小物件的保留

## 暂不展开的内容
- 不揭示阿绣身份
- 不展开司命体系
- 不急于抛出主线真相
"""

LOCKED_TEXT = """潮气贴着木板往上返。孟浮灯把盐货挪到棚下时，肩背已经酸得发木。他把那截短短的线头塞进袖口里，才低头去补剩下的裂口。"""


class StoryStateTest(unittest.TestCase):
    def write_fixture(self, root: Path) -> None:
        (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
        (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
        (root / "03_locked/state").mkdir(parents=True, exist_ok=True)
        (root / "01_inputs/tasks/generated").mkdir(parents=True, exist_ok=True)
        (root / "03_locked/canon/ch01_state.md").write_text(CHAPTER_STATE_TEXT, encoding="utf-8")
        (root / "03_locked/chapters/ch01_scene09.md").write_text(LOCKED_TEXT, encoding="utf-8")
        (root / "01_inputs/tasks/generated/2026-04-03-016_ch01_scene09_auto.md").write_text(TASK_TEXT, encoding="utf-8")

    def test_update_story_state_on_lock_creates_json_and_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_fixture(root)

            result = update_story_state_on_lock(
                root,
                TASK_TEXT,
                "03_locked/chapters/ch01_scene09.md",
                chapter_state_path="03_locked/canon/ch01_state.md",
            )

            self.assertTrue((root / result["story_state_file"]).exists())
            self.assertTrue((root / result["story_state_patch_file"]).exists())
            self.assertTrue((root / result["story_state_diff_file"]).exists())
            self.assertTrue((root / result["story_state_snapshot_file"]).exists())

            state = StoryState.load(root / STORY_STATE_REL_PATH)
            self.assertEqual(state.last_locked_scene, "ch01_scene09")
            self.assertIn("EVENT-009", state.timeline.recent_events)
            self.assertEqual(state.characters["protagonist"].location, "码头")
            self.assertIn("红绳", state.characters["protagonist"].known_facts)
            self.assertTrue(any(item.name == "平安符" for item in state.items))
            self.assertTrue(any(p.description == "不揭示阿绣身份" for p in state.unresolved_promises))

            patch_data = json.loads((root / result["story_state_patch_file"]).read_text(encoding="utf-8"))
            self.assertEqual(patch_data["task_id"], "2026-04-03-016")
            self.assertEqual(patch_data["locked_file"], "03_locked/chapters/ch01_scene09.md")
            self.assertIn("recent_events_to_add", patch_data["timeline_updates"])
            self.assertIn("protagonist", patch_data["character_updates"])
            self.assertTrue(patch_data["decision_reason"])

    def test_update_story_state_merges_with_existing_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_fixture(root)
            initial_state = {
                "timeline": {"current_book_time": "次日白天", "recent_events": ["EVENT-008"]},
                "characters": {
                    "protagonist": {
                        "location": "码头",
                        "physical_state": "疲惫",
                        "mental_state": "克制",
                        "known_facts": ["平安符背面的“阿绣”"],
                        "active_goals": ["维持日常求活与码头做活"],
                        "open_tensions": ["放不下“阿绣”"]
                    }
                },
                "unresolved_promises": [],
                "revealed_secrets": [],
                "items": [],
                "relationship_deltas": [],
                "last_locked_scene": "ch01_scene08"
            }
            (root / STORY_STATE_REL_PATH).write_text(json.dumps(initial_state, ensure_ascii=False, indent=2), encoding="utf-8")

            update_story_state_on_lock(
                root,
                TASK_TEXT,
                "03_locked/chapters/ch01_scene09.md",
                chapter_state_path="03_locked/canon/ch01_state.md",
            )

            state = load_story_state(root)
            self.assertEqual(state.timeline.current_book_time, "次日白天")
            self.assertEqual(state.timeline.recent_events, ["EVENT-008", "EVENT-009"])
            self.assertIn("维持日常求活与码头做活", state.characters["protagonist"].active_goals)
            self.assertIn("平安符背面的“阿绣”", state.characters["protagonist"].known_facts)

    def test_diff_log_contains_added_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_fixture(root)

            result = update_story_state_on_lock(
                root,
                TASK_TEXT,
                "03_locked/chapters/ch01_scene09.md",
                chapter_state_path="03_locked/canon/ch01_state.md",
            )
            diff_text = (root / result["story_state_diff_file"]).read_text(encoding="utf-8")
            self.assertIn("## Added", diff_text)
            self.assertIn("timeline.current_book_time", diff_text)
            self.assertIn("characters.protagonist.location", diff_text)

    def test_patch_proposal_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_fixture(root)

            result = update_story_state_on_lock(
                root,
                TASK_TEXT,
                "03_locked/chapters/ch01_scene09.md",
                chapter_state_path="03_locked/canon/ch01_state.md",
            )
            patch_data = json.loads((root / result["story_state_patch_file"]).read_text(encoding="utf-8"))

            self.assertIn("unresolved_promises_to_add", patch_data)
            self.assertIn("item_updates", patch_data)
            self.assertEqual(patch_data["character_updates"]["protagonist"]["location"], "码头")
            self.assertTrue(any(item["name"] == "线头" for item in patch_data["item_updates"]))

    def test_story_state_uses_generic_tension_labels_instead_of_specific_name_binding(self) -> None:
        chapter_state_text = """# ch01 当前状态

## 当前主角状态
- 他尚未形成明确调查行动，但已经无法把这个名字当作普通死者名讳轻易放下
"""

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon/ch01_state.md").write_text(chapter_state_text, encoding="utf-8")
            (root / "03_locked/chapters/ch01_scene09.md").write_text("孟浮灯停顿了一下，还是没有主动追查。", encoding="utf-8")

            result = update_story_state_on_lock(
                root,
                TASK_TEXT,
                "03_locked/chapters/ch01_scene09.md",
                chapter_state_path="03_locked/canon/ch01_state.md",
            )

            state = StoryState.load(root / STORY_STATE_REL_PATH)

        self.assertTrue(result["story_state_file"].endswith("story_state.json"))
        self.assertIn("被未解线索持续牵动", state.characters["protagonist"].mental_state)
        self.assertIn("在不主动追查的前提下继续压住这条未解线索", state.characters["protagonist"].active_goals)
        self.assertNotIn("阿绣", state.characters["protagonist"].mental_state)

    def test_extract_item_candidates_keeps_generic_item_names_without_special_case_table(self) -> None:
        items = extract_item_candidates("他把平安符塞回袖里，又捡起红绳和短短的线头。")

        self.assertIn("平安符", items)
        self.assertIn("红绳", items)
        self.assertIn("线头", items)

    def test_story_state_filters_sentence_fragments_from_items_and_known_facts(self) -> None:
        dirty_state = StoryState.from_dict(
            {
                "timeline": {"current_book_time": "unknown", "recent_events": []},
                "characters": {
                    "protagonist": {
                        "location": "码头",
                        "physical_state": "unknown",
                        "mental_state": "unknown",
                        "known_facts": ["红绳", "孟浮灯松开麻绳", "而是催命符"],
                        "active_goals": ["维持日常求活", "过码头卸货时被缆绳"],
                        "open_tensions": ["一个名字被录入了册", "未解线索"],
                    }
                },
                "unresolved_promises": [],
                "revealed_secrets": [],
                "items": [
                    {"id": "ITEM-001", "name": "红绳", "owner": "孟浮灯", "status": "贴身保留", "last_seen_in": "ch01_scene01"},
                    {"id": "ITEM-002", "name": "孟浮灯松开麻绳", "owner": "孟浮灯", "status": "待确认", "last_seen_in": "ch01_scene01"},
                ],
                "relationship_deltas": [],
                "last_locked_scene": "ch01_scene01",
            }
        )

        cleaned = clean_story_state(dirty_state)

        protagonist = cleaned.characters["protagonist"]
        self.assertEqual(protagonist.known_facts, ["红绳"])
        self.assertEqual(protagonist.active_goals, ["维持日常求活"])
        self.assertEqual(protagonist.open_tensions, ["未解线索"])
        self.assertEqual([item.name for item in cleaned.items], ["红绳"])

    def test_story_state_bootstraps_protagonist_name_and_location_from_task_and_chapter_state(self) -> None:
        task_text = """# task_id
2026-04-07-001

# goal
承接上一场，继续保持渡口求活与低烈度推进。

# chapter_state
03_locked/canon/ch02_state.md
"""
        chapter_state_text = """# ch02 当前状态

## 当前主角状态
- 沈砚仍处于底层求活状态
- 他尚未形成明确调查行动，但已经无法把这个名字轻易放下

## 已锁定线索
- 木牌背面有旧划痕
"""
        locked_text = "沈砚把麻袋拖到渡口棚下，肩背发木，却还是把那块木牌塞回袖里。"

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/chapters").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon/ch02_state.md").write_text(chapter_state_text, encoding="utf-8")
            (root / "03_locked/chapters/ch02_scene01.md").write_text(locked_text, encoding="utf-8")

            update_story_state_on_lock(
                root,
                task_text,
                "03_locked/chapters/ch02_scene01.md",
                chapter_state_path="03_locked/canon/ch02_state.md",
            )

            state = StoryState.load(root / STORY_STATE_REL_PATH)

        self.assertEqual(state.characters["protagonist"].location, "渡口")
        self.assertTrue(any(item.owner == "沈砚" for item in state.items))
        self.assertTrue(any(item.source == "沈砚" for item in state.relationship_deltas) or not state.relationship_deltas)

    def test_rebuild_story_state_from_locked_recreates_state_from_scratch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.write_fixture(root)
            (root / "03_locked/chapters/ch01_scene01.md").write_text("孟浮灯在运河边做活，天光发白。", encoding="utf-8")
            (root / "02_working/canon_updates").mkdir(parents=True, exist_ok=True)
            (root / "02_working/canon_updates/ch01_scene09_story_state_patch.json").write_text("{}", encoding="utf-8")
            dirty_state = {
                "timeline": {"current_book_time": "错误时间", "recent_events": ["EVENT-999"]},
                "characters": {
                    "protagonist": {
                        "location": "错误地点",
                        "physical_state": "错误状态",
                        "mental_state": "错误状态",
                        "known_facts": ["脏数据"],
                        "active_goals": [],
                        "open_tensions": []
                    }
                },
                "unresolved_promises": [],
                "revealed_secrets": [],
                "items": [],
                "relationship_deltas": [
                    {
                        "id": "REL-999",
                        "source": "孟浮灯",
                        "target": "这种改变",
                        "delta": "脏关系",
                        "introduced_in": "bad_scene",
                        "status": "active"
                    }
                ],
                "last_locked_scene": "bad_scene"
            }
            (root / STORY_STATE_REL_PATH).write_text(json.dumps(dirty_state, ensure_ascii=False, indent=2), encoding="utf-8")

            result = rebuild_story_state_from_locked(root)

            self.assertEqual(result["scene_count"], 2)
            self.assertEqual(result["processed_scenes"][0]["scene"], "ch01_scene01")
            self.assertEqual(result["processed_scenes"][1]["scene"], "ch01_scene09")
            self.assertIsNone(result["processed_scenes"][0]["task_file"])
            self.assertEqual(result["processed_scenes"][1]["task_file"], "01_inputs/tasks/generated/2026-04-03-016_ch01_scene09_auto.md")

            rebuilt_state = load_story_state(root)
            self.assertNotIn("EVENT-999", rebuilt_state.timeline.recent_events)
            self.assertEqual(rebuilt_state.last_locked_scene, "ch01_scene09")
            self.assertFalse(any(item.target == "这种改变" for item in rebuilt_state.relationship_deltas))
            self.assertTrue((root / "03_locked/state/history/ch01_scene01_story_state_snapshot.json").exists())
            self.assertTrue((root / "03_locked/state/history/ch01_scene09_story_state_snapshot.json").exists())


if __name__ == "__main__":
    unittest.main()
