import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import app.deepseek_reviewer as deepseek_module
import app.review_scene as review_scene_module
from app.review_models import load_repair_plan, load_structured_review_result


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


class DeepSeekReviewerTest(unittest.TestCase):
    def test_review_scene_with_deepseek_returns_validated_dict(self) -> None:
        fake_client = FakeClient(
            [
                json.dumps(
                    {
                        "status": "revise",
                        "summary": "场景方向正确，但动作牵引还不够明确。",
                        "issues": [
                            {
                                "id": "ISSUE-001",
                                "type": "scene_purpose",
                                "severity": "high",
                                "scope": "scene",
                                "target": "scene_060",
                                "message": "动作牵引不够明确。",
                                "suggested_action": "rewrite_local",
                            }
                        ],
                        "strengths": ["整体方向正确。"],
                        "decision_reason": "核心目标尚未完全落地。",
                    },
                    ensure_ascii=False,
                )
            ]
        )
        previous_factory = deepseek_module.create_deepseek_client
        deepseek_module.create_deepseek_client = lambda api_key=None, api_key_env=None: fake_client
        try:
            result = deepseek_module.review_scene_with_deepseek(
                "场景正文",
                {"task_id": "scene_060", "api_key": "test-key"},
                {"task_id": "scene_060"},
            )
        finally:
            deepseek_module.create_deepseek_client = previous_factory

        self.assertEqual(result["task_id"], "scene_060")
        self.assertEqual(getattr(result["status"], "value", result["status"]), "revise")
        self.assertEqual(result["issues"][0]["id"], "ISSUE-001")
        self.assertEqual(result["decision_reason"], "核心目标尚未完全落地。")

    def test_review_scene_with_deepseek_degrades_on_invalid_json(self) -> None:
        fake_client = FakeClient(["not-json"])
        previous_factory = deepseek_module.create_deepseek_client
        deepseek_module.create_deepseek_client = lambda api_key=None, api_key_env=None: fake_client
        try:
            result = deepseek_module.review_scene_with_deepseek(
                "场景正文",
                {"task_id": "scene_061", "api_key": "test-key"},
                {},
            )
        finally:
            deepseek_module.create_deepseek_client = previous_factory

        self.assertEqual(getattr(result["status"], "value", result["status"]), "manual_intervention")
        self.assertIn("JSON 解析失败", result["decision_reason"])

    def test_review_scene_with_deepseek_degrades_on_schema_failure(self) -> None:
        fake_client = FakeClient(
            [
                json.dumps(
                    {
                        "task_id": "scene_062",
                        "status": "bad-status",
                        "summary": "错误输出",
                        "issues": [],
                        "strengths": [],
                        "decision_reason": "bad",
                    },
                    ensure_ascii=False,
                )
            ]
        )
        previous_factory = deepseek_module.create_deepseek_client
        deepseek_module.create_deepseek_client = lambda api_key=None, api_key_env=None: fake_client
        try:
            result = deepseek_module.review_scene_with_deepseek(
                "场景正文",
                {"task_id": "scene_062", "api_key": "test-key"},
                {},
            )
        finally:
            deepseek_module.create_deepseek_client = previous_factory

        self.assertEqual(getattr(result["status"], "value", result["status"]), "manual_intervention")
        self.assertIn("schema 校验失败", result["decision_reason"])

    def test_parse_deepseek_review_result_normalizes_extended_issue_enums(self) -> None:
        result = deepseek_module.parse_deepseek_review_result(
            "scene_062b",
            json.dumps(
                {
                    "task_id": "scene_062b",
                    "status": "revise",
                    "summary": "需要补足结构推进。",
                    "issues": [
                        {
                            "id": "ISSUE-001",
                            "type": "information_gain",
                            "severity": "high",
                            "scope": "global",
                            "target": "scene_062b",
                            "message": "缺少新信息。",
                            "suggested_action": "rewrite_local",
                        },
                        {
                            "id": "ISSUE-002",
                            "type": "state_transition_evidence",
                            "severity": "medium",
                            "scope": "weird",
                            "target": "scene_062b",
                            "message": "缺少状态变化证据。",
                            "suggested_action": "revise_local",
                        },
                    ],
                    "strengths": ["氛围稳定。"],
                    "decision_reason": "结构推进不足。",
                },
                ensure_ascii=False,
            ),
        )

        self.assertEqual(result["issues"][0]["type"], "knowledge")
        self.assertEqual(result["issues"][0]["scope"], "global")
        self.assertEqual(result["issues"][1]["type"], "continuity")
        self.assertEqual(result["issues"][1]["scope"], "scene")

    def test_parse_deepseek_review_result_falls_back_for_unknown_state_like_types(self) -> None:
        result = deepseek_module.parse_deepseek_review_result(
            "scene_062c",
            json.dumps(
                {
                    "task_id": "scene_062c",
                    "status": "revise",
                    "summary": "需要修正物件状态。",
                    "issues": [
                        {
                            "id": "ISSUE-001",
                            "type": "artifact_state",
                            "severity": "high",
                            "scope": "chapter",
                            "target": "scene_062c",
                            "message": "物件状态不一致。",
                            "suggested_action": "rewrite_scene",
                        }
                    ],
                    "strengths": ["已有清晰动作线。"],
                    "decision_reason": "需要先修正状态一致性。",
                },
                ensure_ascii=False,
            ),
        )

        self.assertEqual(result["issues"][0]["type"], "continuity")

    def test_review_scene_with_deepseek_retries_transient_failure(self) -> None:
        fake_client = FakeClient(
            [
                TimeoutError("temporary timeout"),
                json.dumps(
                    {
                        "task_id": "scene_063",
                        "status": "lock",
                        "summary": "当前场景可锁定。",
                        "issues": [],
                        "strengths": ["目标已完成。"],
                        "decision_reason": "无阻塞问题。",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        sleeps: list[float] = []
        previous_factory = deepseek_module.create_deepseek_client
        previous_sleep = deepseek_module.time.sleep
        deepseek_module.create_deepseek_client = lambda api_key=None, api_key_env=None: fake_client
        deepseek_module.time.sleep = lambda seconds: sleeps.append(seconds)
        try:
            result = deepseek_module.review_scene_with_deepseek(
                "场景正文",
                {"task_id": "scene_063", "api_key": "test-key", "max_retries": 2, "retry_backoff_base": 0.25},
                {},
            )
        finally:
            deepseek_module.create_deepseek_client = previous_factory
            deepseek_module.time.sleep = previous_sleep

        self.assertEqual(getattr(result["status"], "value", result["status"]), "lock")
        self.assertEqual(fake_client.chat.completions.calls, 2)
        self.assertEqual(sleeps, [0.25])

    def test_review_scene_file_uses_deepseek_without_breaking_contracts(self) -> None:
        task_text = """# task_id
scene_064-R1

# goal
审查当前 scene。

# based_on
02_working/drafts/previous.md

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/ch01_scene64_v2.md
"""
        structured_result = {
            "task_id": "scene_064-R1",
            "status": "manual_intervention",
            "summary": "DeepSeek reviewer 输出不可用，转人工介入。",
            "issues": [],
            "strengths": [],
            "decision_reason": "DeepSeek reviewer schema 校验失败：bad json",
        }
        config = {
            "reviewer": {
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-chat",
                "request_timeout": 30,
                "task_max_chars": 2000,
                "chapter_state_max_chars": 2000,
                "based_on_max_chars": 2000,
                "draft_max_chars": 2000,
            }
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "01_inputs/tasks").mkdir(parents=True, exist_ok=True)
            (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
            (root / "01_inputs/tasks/current_task.md").write_text(task_text, encoding="utf-8")
            (root / "02_working/drafts/current.md").write_text("当前场景正文", encoding="utf-8")
            (root / "02_working/drafts/previous.md").write_text("前文", encoding="utf-8")
            (root / "03_locked/canon/ch01_state.md").write_text("章节状态", encoding="utf-8")

            previous_root = review_scene_module.ROOT
            previous_reviewer = review_scene_module.review_scene_with_deepseek
            review_scene_module.ROOT = root
            review_scene_module.review_scene_with_deepseek = lambda scene_text, scene_metadata, canon_context: structured_result
            try:
                result, out_path = review_scene_module.review_scene_file(config, "02_working/drafts/current.md")
            finally:
                review_scene_module.ROOT = previous_root
                review_scene_module.review_scene_with_deepseek = previous_reviewer

            self.assertEqual(result["task_id"], "scene_064-R1")
            self.assertEqual(result["verdict"], "revise")
            self.assertIn("force_manual_intervention_reason", result)
            self.assertTrue((root / out_path).exists())

            structured = load_structured_review_result(root, "scene_064-R1")
            repair_plan = load_repair_plan(root, "scene_064-R1")
            self.assertEqual(structured.status.value, "manual_intervention")
            self.assertEqual(repair_plan.task_id, "scene_064-R1")

    def test_review_scene_file_passes_api_key_env_to_deepseek(self) -> None:
        task_text = """# task_id
scene_065

# goal
审查当前 scene。

# based_on
02_working/drafts/previous.md

# chapter_state
03_locked/canon/ch01_state.md

# output_target
02_working/drafts/ch01_scene65.md
"""
        captured: dict[str, object] = {}
        config = {
            "reviewer": {
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-chat",
                "api_key_env": "sk-inline-test",
                "request_timeout": 30,
                "task_max_chars": 2000,
                "chapter_state_max_chars": 2000,
                "based_on_max_chars": 2000,
                "draft_max_chars": 2000,
            }
        }

        def fake_review_scene_with_deepseek(scene_text, scene_metadata, canon_context):
            captured["scene_metadata"] = scene_metadata
            captured["canon_context"] = canon_context
            return {
                "task_id": "scene_065",
                "status": "lock",
                "summary": "可锁定。",
                "issues": [],
                "strengths": [],
                "decision_reason": "输出正常。",
            }

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "01_inputs/tasks").mkdir(parents=True, exist_ok=True)
            (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
            (root / "01_inputs/tasks/current_task.md").write_text(task_text, encoding="utf-8")
            (root / "02_working/drafts/current.md").write_text("当前场景正文", encoding="utf-8")
            (root / "02_working/drafts/previous.md").write_text("前文", encoding="utf-8")
            (root / "03_locked/canon/ch01_state.md").write_text("章节状态", encoding="utf-8")

            previous_root = review_scene_module.ROOT
            previous_reviewer = review_scene_module.review_scene_with_deepseek
            review_scene_module.ROOT = root
            review_scene_module.review_scene_with_deepseek = fake_review_scene_with_deepseek
            try:
                result, _ = review_scene_module.review_scene_file(config, "02_working/drafts/current.md")
            finally:
                review_scene_module.ROOT = previous_root
                review_scene_module.review_scene_with_deepseek = previous_reviewer

        self.assertEqual(result["task_id"], "scene_065")
        self.assertEqual(captured["scene_metadata"]["api_key_env"], "sk-inline-test")

    def test_review_scene_file_deepseek_path_fills_structural_fields(self) -> None:
        task_text = """# task_id
scene_066

# goal
承接上一场，把尸体运到处理地点，并让主角确认名字后先压下不说。

# based_on
02_working/drafts/previous.md

# chapter_state
03_locked/canon/ch01_state.md

# required_information_gain
- 孟浮灯确认“阿绣”确实是平安符背面残存的字。

# output_target
02_working/drafts/ch01_scene66.md
"""
        config = {
            "reviewer": {
                "provider": "deepseek",
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-chat",
                "request_timeout": 30,
                "task_max_chars": 2000,
                "chapter_state_max_chars": 2000,
                "based_on_max_chars": 2000,
                "draft_max_chars": 2000,
            }
        }

        def fake_review_scene_with_deepseek(scene_text, scene_metadata, canon_context):
            return {
                "task_id": "scene_066",
                "status": "lock",
                "summary": "可锁定。",
                "issues": [],
                "strengths": [],
                "decision_reason": "输出正常。",
            }

        draft_text = "孟浮灯把尸体运到坡后的浅坑里，确认平安符背后那两个字确实是阿绣，又把红绳和符先裹进油布里，决定今夜不对老张头提起。"

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "01_inputs/tasks").mkdir(parents=True, exist_ok=True)
            (root / "02_working/drafts").mkdir(parents=True, exist_ok=True)
            (root / "03_locked/canon").mkdir(parents=True, exist_ok=True)
            (root / "01_inputs/tasks/current_task.md").write_text(task_text, encoding="utf-8")
            (root / "02_working/drafts/current.md").write_text(draft_text, encoding="utf-8")
            (root / "02_working/drafts/previous.md").write_text("孟浮灯在船上看见泡烂的平安符。", encoding="utf-8")
            (root / "03_locked/canon/ch01_state.md").write_text("阿绣目前只是被记住，还没有发展成调查念头。", encoding="utf-8")

            previous_root = review_scene_module.ROOT
            previous_reviewer = review_scene_module.review_scene_with_deepseek
            review_scene_module.ROOT = root
            review_scene_module.review_scene_with_deepseek = fake_review_scene_with_deepseek
            try:
                result, _ = review_scene_module.review_scene_file(config, "02_working/drafts/current.md")
            finally:
                review_scene_module.ROOT = previous_root
                review_scene_module.review_scene_with_deepseek = previous_reviewer

        self.assertEqual(result["verdict"], "lock")
        self.assertIn("information_gain", result)
        self.assertTrue(result["information_gain"]["has_new_information"])
        self.assertIn("plot_progress", result)
        self.assertTrue(result["plot_progress"]["has_plot_progress"])
        self.assertIn("character_decision", result)
        self.assertTrue(result["character_decision"]["has_decision_or_behavior_shift"])


if __name__ == "__main__":
    unittest.main()
