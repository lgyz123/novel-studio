import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests
import yaml
from issue_filters import filter_shared_issues, is_mostly_english
from jsonschema import validate


ROOT = Path(__file__).resolve().parent.parent


def read_text(rel_path: str) -> str:
    path = ROOT / rel_path
    return path.read_text(encoding="utf-8")


def save_text(rel_path: str, content: str) -> None:
    path = ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_yaml(rel_path: str) -> dict:
    path = ROOT / rel_path
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clip_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[已截断]"


def call_ollama(
    model: str,
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    num_ctx: int,
    temperature: float,
    timeout: int,
    num_predict: int,
    response_format: Any = None,
) -> dict:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "num_ctx": num_ctx,
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    if response_format is not None:
        payload["format"] = response_format

    print(f"正在请求 Reviewer 模型: {model} @ {base_url}")
    last_error: Exception | None = None
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as error:
            last_error = error
            status_code = error.response.status_code if error.response is not None else None
            if status_code is None or status_code < 500 or attempt >= max_attempts:
                raise
            print(f"Reviewer 请求失败（HTTP {status_code}），正在重试 {attempt}/{max_attempts}...")
            time.sleep(min(attempt, 3))
        except requests.exceptions.RequestException as error:
            last_error = error
            if attempt >= max_attempts:
                raise
            print(f"Reviewer 请求异常，正在重试 {attempt}/{max_attempts}...")
            time.sleep(min(attempt, 3))

    assert last_error is not None
    raise last_error


def summarize_response_for_debug(response_data: dict) -> str:
    message = response_data.get("message", {})
    summary = {
        "top_level_keys": sorted(response_data.keys()),
        "message_keys": sorted(message.keys()) if isinstance(message, dict) else [],
        "done": response_data.get("done"),
        "done_reason": response_data.get("done_reason"),
        "prompt_eval_count": response_data.get("prompt_eval_count"),
        "eval_count": response_data.get("eval_count"),
        "content_length": len(message.get("content", "")) if isinstance(message, dict) and isinstance(message.get("content"), str) else 0,
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


def extract_message_text(response_data: dict) -> str:
    message = response_data.get("message", {}) if isinstance(response_data, dict) else {}

    candidates = [
        message.get("content") if isinstance(message, dict) else None,
        message.get("reasoning") if isinstance(message, dict) else None,
        message.get("thinking") if isinstance(message, dict) else None,
        response_data.get("response") if isinstance(response_data, dict) else None,
        response_data.get("content") if isinstance(response_data, dict) else None,
        response_data.get("reasoning") if isinstance(response_data, dict) else None,
        response_data.get("thinking") if isinstance(response_data, dict) else None,
    ]

    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def extract_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    if not text:
        raise ValueError("Reviewer 模型返回空内容")

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Reviewer 没有输出可提取的 JSON")

    return json.loads(match.group(0))


def validate_review_content(result: dict) -> None:
    summary = str(result.get("summary", "")).strip()
    major_issues = [item for item in result.get("major_issues", []) if str(item).strip()]
    minor_issues = [item for item in result.get("minor_issues", []) if str(item).strip()]

    if not summary:
        raise ValueError("Reviewer 输出缺少有效 summary")

    if result.get("verdict") in {"revise", "rewrite"} and not (major_issues or minor_issues):
        raise ValueError("Reviewer 给出了 revise/rewrite，但没有任何具体修改意见")

    if result.get("task_goal_fulfilled") is False and not (major_issues or minor_issues):
        raise ValueError("Reviewer 判定任务未完成，但没有给出具体问题")


def build_chinese_issue_fallback(verdict: str, raw_review_text: str) -> tuple[list[str], list[str], str]:
    lower_text = raw_review_text.lower()

    if verdict == "lock":
        return [], [], "当前 scene 已满足任务目标与约束条件，可直接锁定。"

    major_issues: list[str] = []
    minor_issues: list[str] = []

    if "too short" in lower_text or "500-900" in raw_review_text or "200-250" in lower_text:
        major_issues.append("篇幅与动作承载量偏弱，导致本场的完成度不足。")

    if "missing the hesitation" in lower_text or "influences action" in lower_text:
        major_issues.append("“阿绣”之名被想起后，对现实动作的轻微牵引还不够明确。")

    if "lingering" in lower_text or "fatigue" in lower_text or "low intensity" in lower_text:
        minor_issues.append("疲惫后的动作偏移与停顿感还能再落得更实一些。")

    if "closure" in lower_text or "not enough" in lower_text:
        minor_issues.append("场景尾部的收束略弱，闭环感还可以再加强。")

    if verdict == "rewrite":
        if not major_issues:
            major_issues.append("当前 scene 在方向或约束执行上存在明显偏差，需要整体重写。")
        summary = "当前 scene 存在方向性问题，建议整体重写后再进入审稿。"
    else:
        if not major_issues:
            major_issues.append("方向基本正确，但本场关键动作的完成度仍不足。")
        summary = "当前 scene 方向正确，但动作牵引与场景闭环仍不够完整，更适合先小修。"

    return major_issues[:3], minor_issues[:3], summary


def normalize_review_result(result: dict, raw_review_text: str, task_text: str | None = None) -> dict:
    def raw_review_has_strong_negative_signal(text: str) -> bool:
        lower_text = text.lower()
        negative_markers = [
            "reject",
            "not acceptable",
            "does not meet",
            "doesn't meet",
            "fails the task",
            "fails to meet",
            "too short",
            "not in the required setting",
            "not in the dock",
            "missing the core goal",
            "core line is missing",
            "is too short",
            "should reject",
        ]
        return any(marker in lower_text for marker in negative_markers)

    def is_bad_issue(text: str) -> bool:
        text = text.strip()

        bad_exact_or_prefix = [
            "The task:",
            "Must not",
            "We need to check",
            "But maybe",
            "So maybe",
            "No new characters.",
            "No new characters",
            "不引入新人物。",
            "不新增制度性设定。",
            "保持单视角。",
        ]
        if any(text.startswith(prefix) for prefix in bad_exact_or_prefix):
            return True

        if re.search(r"[A-Za-z]{3,}", text):
            return True

        if task_text:
            short_lines = [
                line.strip("- ").strip()
                for line in task_text.splitlines()
                if line.strip()
            ]
            for line in short_lines:
                if len(line) >= 4 and text == line:
                    return True

        return False

    def clean_list(items: list[str]) -> list[str]:
        cleaned = []

        for item in items:
            text = str(item).strip()
            if not text:
                continue
            if is_bad_issue(text):
                continue
            cleaned.append(text)

        return cleaned

    verdict = result.get("verdict", "revise")
    cleaned_major = clean_list(filter_shared_issues(result.get("major_issues", []), task_text=task_text, limit=3))
    cleaned_minor = clean_list(filter_shared_issues(result.get("minor_issues", []), task_text=task_text, limit=3))
    summary = str(result.get("summary", "")).strip()

    if verdict == "lock" and raw_review_has_strong_negative_signal(raw_review_text):
        verdict = "revise"
        result["verdict"] = "revise"
        result["recommended_next_step"] = "create_revision_task"
        if not cleaned_major:
            cleaned_major = ["原始审稿明确指出当前草稿未满足核心任务或关键约束，不应直接锁定。"]

    if verdict == "rewrite" and not cleaned_major:
        verdict = "revise"
        result["verdict"] = "revise"
        result["recommended_next_step"] = "create_revision_task"

    if is_mostly_english(summary) or not summary:
        _, _, fallback_summary = build_chinese_issue_fallback(verdict, raw_review_text)
        summary = fallback_summary

    if verdict in {"revise", "rewrite"} and not (cleaned_major or cleaned_minor):
        cleaned_major, cleaned_minor, fallback_summary = build_chinese_issue_fallback(verdict, raw_review_text)
        summary = fallback_summary

    if not cleaned_major and verdict in {"revise", "rewrite"}:
        cleaned_major = ["当前草稿未充分完成 task 的核心推进目标。"]

    rewrite_hard_markers = [
        "角色越界",
        "设定越界",
        "节奏失控",
        "文体错误",
        "方向错误",
        "场景功能错位",
    ]
    major_text = " ".join(cleaned_major)
    if verdict == "rewrite":
        if not any(marker in major_text for marker in rewrite_hard_markers):
            verdict = "revise"
            result["verdict"] = "revise"
            result["recommended_next_step"] = "create_revision_task"

    positive_summary_markers = ["方向正确", "基本满足", "可作为终稿"]
    negative_summary_markers = ["未完成", "不足", "需要小修", "仍需", "还需", "不够", "偏弱"]
    heavy_minor_markers = ["核心推进", "未完成", "不足", "偏弱", "不够", "需要补", "需要加强"]
    minor_is_light = len(cleaned_minor) <= 2 and not any(
        any(marker in item for marker in heavy_minor_markers) for item in cleaned_minor
    )
    if (
        verdict == "revise"
        and len(cleaned_major) == 1
        and any(marker in summary for marker in positive_summary_markers)
        and not any(marker in summary for marker in negative_summary_markers)
        and minor_is_light
    ):
        cleaned_minor = cleaned_major + cleaned_minor
        cleaned_major = []
        verdict = "lock"
        result["verdict"] = "lock"
        result["recommended_next_step"] = "lock_scene"

    if verdict != "lock":
        result["task_goal_fulfilled"] = False
    else:
        result["task_goal_fulfilled"] = True

    result["major_issues"] = cleaned_major
    result["minor_issues"] = cleaned_minor
    result["summary"] = summary

    return result


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[。！？.!?])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def infer_verdict_from_text(text: str) -> str:
    lower_text = text.lower()

    rewrite_markers = [
        "rewrite",
        "must rewrite",
        "should rewrite",
        "direction is wrong",
        "functionally fails",
        "violates constraints badly",
    ]
    strong_revise_markers = [
        "revise",
        "needs revision",
        "not enough",
        "too short",
        "too long",
        "should tighten",
        "should trim",
        "needs more work",
        "does not satisfy",
        "fails to",
    ]
    lock_markers = [
        "can be locked",
        "can lock",
        "can be lock",
        "satisfy constraints",
        "satisfies all constraints",
        "seems to satisfy constraints",
        "satisfy all constraints",
        "no major issues",
        "no minor issues",
        "suitable to lock",
        "lock_scene",
        "can be directly locked",
    ]

    if any(marker in lower_text for marker in rewrite_markers):
        return "rewrite"
    if any(marker in lower_text for marker in lock_markers):
        return "lock"
    if any(marker in lower_text for marker in strong_revise_markers):
        return "revise"

    return "revise"


def extract_issue_candidates(text: str) -> tuple[list[str], list[str]]:
    sentences = split_sentences(text)
    major_keywords = (
        "major issue",
        "violat",
        "wrong",
        "fails",
        "not satisfy",
        "out of bounds",
        "too much",
        "investigation",
        "new characters",
        "new institutions",
    )
    minor_keywords = (
        "minor issue",
        "too short",
        "too long",
        "slightly",
        "could",
        "maybe",
        "approximate",
        "length",
        "check",
    )

    major_issues: list[str] = []
    minor_issues: list[str] = []

    for sentence in sentences:
        lower_sentence = sentence.lower()
        if any(keyword in lower_sentence for keyword in major_keywords):
            major_issues.append(sentence)
        elif any(keyword in lower_sentence for keyword in minor_keywords):
            minor_issues.append(sentence)

    return major_issues[:3], minor_issues[:3]


def build_local_review_fallback(task_id: str, raw_review_text: str) -> dict:
    verdict = infer_verdict_from_text(raw_review_text)
    major_issues, minor_issues = extract_issue_candidates(raw_review_text)

    if verdict == "lock":
        summary = "审稿分析认为当前 scene 基本满足任务约束、人物边界与低烈度推进要求，可直接锁定。"
        task_goal_fulfilled = True
        recommended_next_step = "lock_scene"
        major_issues = []
        minor_issues = []
    elif verdict == "rewrite":
        summary = "审稿分析认为当前 scene 存在方向性或约束性问题，建议整体重写。"
        task_goal_fulfilled = False
        recommended_next_step = "rewrite_scene"
        if not major_issues:
            major_issues = ["当前审稿分析指向重写，但原始输出未提供足够结构化的问题列表，需人工补充复核。"]
    else:
        summary = "审稿分析认为当前 scene 方向基本正确，但仍有若干问题需要小修。"
        task_goal_fulfilled = False
        recommended_next_step = "create_revision_task"
        if not (major_issues or minor_issues):
            minor_issues = ["原始审稿输出未按 JSON 返回，需人工根据审稿分析补充细化修改点。"]

    return {
        "task_id": task_id,
        "verdict": verdict,
        "task_goal_fulfilled": task_goal_fulfilled,
        "major_issues": major_issues,
        "minor_issues": minor_issues,
        "recommended_next_step": recommended_next_step,
        "summary": summary,
    }


def extract_markdown_field(task_text: str, field_name: str) -> str | None:
    import re

    pattern = rf"(?ms)^#\s*{field_name}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, task_text)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


def build_review_prompt(
    task_text: str,
    chapter_state: str,
    based_on_text: str,
    draft_text: str,
) -> str:
    return f"""请审查下面这段 scene 草稿。

你只能输出一个合法 JSON 对象。
禁止先输出分析过程、英文说明、推理草稿或自然语言结论。
如果判断可以锁定，也必须把理由写进 summary 字段。

【当前任务】
{task_text}

【当前章节状态】
{chapter_state}

【直接前文 / 基准文本】
{based_on_text}

【待审草稿】
{draft_text}

再次强调：你的最终输出必须是单个 JSON 对象本身，首字符必须是 {{，末字符必须是 }}。
"""
def extract_reviewer_json(
    config: dict,
    task_id: str,
    raw_review_text: str,
) -> dict:
    system_prompt = """你是 JSON 提纯助手。
你的任务是把一段审稿意见提炼成一个合法 JSON 对象。
不要输出解释，不要输出 markdown，不要输出代码块，只输出 JSON。"""

    user_prompt = f"""请把下面这段审稿意见提炼为合法 JSON。

JSON 必须包含这些字段：
- task_id
- verdict (lock / revise / rewrite)
- task_goal_fulfilled (true / false)
- major_issues (string array)
- minor_issues (string array)
- recommended_next_step (lock_scene / create_revision_task / rewrite_scene)
- summary (string)

task_id 固定为：
{task_id}

下面是待提炼的审稿意见：
{raw_review_text}
"""

    refined = call_ollama(
        model=config["reviewer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["reviewer"]["base_url"],
        num_ctx=config["reviewer"]["num_ctx"],
        temperature=config["reviewer"].get("temperature", 0.1),
        timeout=config["reviewer"]["request_timeout"],
        num_predict=config["reviewer"].get("refine_num_predict", 700),
        response_format={"type": "object"},
    )

    return extract_json_object(extract_message_text(refined))


def review_scene_file(config: dict, draft_rel_path: str) -> tuple[dict, str]:
    draft_text = clip_text(
        read_text(draft_rel_path),
        config["reviewer"].get("draft_max_chars", 3000),
    )

    task_text = clip_text(
        read_text("01_inputs/tasks/current_task.md"),
        config["reviewer"].get("task_max_chars", 2200),
    )
    task_id = extract_markdown_field(task_text, "task_id") or "unknown-task"

    chapter_state_path = extract_markdown_field(task_text, "chapter_state")
    if chapter_state_path:
        chapter_state = clip_text(
            read_text(chapter_state_path),
            config["reviewer"].get("chapter_state_max_chars", 2200),
        )
    else:
        chapter_state = "[未提供 chapter_state]"

    based_on_path = extract_markdown_field(task_text, "based_on")
    if based_on_path:
        based_on_text = clip_text(
            read_text(based_on_path),
            config["reviewer"].get("based_on_max_chars", 2200),
        )
    else:
        based_on_text = "[未提供 based_on]"

    system_prompt = read_text("prompts/reviewer_system.md")
    schema = json.loads(read_text("prompts/reviewer_output_schema.json"))

    user_prompt = build_review_prompt(
        task_text=task_text,
        chapter_state=chapter_state,
        based_on_text=based_on_text,
        draft_text=draft_text,
    )

    raw_response = call_ollama(
        model=config["reviewer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["reviewer"]["base_url"],
        num_ctx=config["reviewer"]["num_ctx"],
        temperature=config["reviewer"].get("temperature", 0.1),
        timeout=config["reviewer"]["request_timeout"],
        num_predict=config["reviewer"].get("num_predict", 900),
        response_format=schema,
    )
    raw_output = extract_message_text(raw_response)

    try:
        result = extract_json_object(raw_output)
    except Exception:
        print("Reviewer 原始输出如下：")
        print("=" * 40)
        print(raw_output)
        print("=" * 40)
        if not raw_output.strip():
            print("Reviewer 原始响应摘要：")
            print(summarize_response_for_debug(raw_response))
            raise ValueError(
                "Reviewer 模型返回空内容；请求已成功到达服务端，但可读输出字段为空，可能是模型空 content 或返回在非标准字段。"
            )
        print("Reviewer 未直接输出 JSON，正在尝试提纯为 JSON...")
        try:
            result = extract_reviewer_json(config, task_id, raw_output)
        except Exception:
            print("Reviewer 二次提纯失败，正在使用本地规则生成兜底审稿结果...")
            result = build_local_review_fallback(task_id, raw_output)

    result = normalize_review_result(result, raw_output, task_text=task_text)
    validate(instance=result, schema=schema)
    validate_review_content(result)

    result["task_id"] = task_id

    out_path = f"02_working/reviews/{task_id}_reviewer.json"
    save_text(out_path, json.dumps(result, ensure_ascii=False, indent=2))
    return result, out_path

def main() -> None:
    try:
        config = load_yaml("app/config.yaml")

        if len(sys.argv) < 2:
            print("用法: python3 app/review_scene.py <scene_draft_path>")
            sys.exit(1)

        result, out_path = review_scene_file(config, sys.argv[1])

        print(f"已保存 reviewer 结果: {out_path}")
        print("审稿结论：", result["verdict"])
        print("建议下一步：", result["recommended_next_step"])

    except FileNotFoundError as e:
        print(f"缺少输入文件: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
    except requests.exceptions.ReadTimeout:
        print("运行失败: reviewer 请求超时")
    except Exception as e:
        print(f"运行失败: {e}")


if __name__ == "__main__":
    main()