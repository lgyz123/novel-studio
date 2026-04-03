import json
import sys
from pathlib import Path

import requests
import yaml
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
) -> str:
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

    print(f"正在请求 Reviewer 模型: {model} @ {base_url}")
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data["message"]["content"]


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

【当前任务】
{task_text}

【当前章节状态】
{chapter_state}

【直接前文 / 基准文本】
{based_on_text}

【待审草稿】
{draft_text}
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
        temperature=0.1,
        timeout=config["reviewer"]["request_timeout"],
        num_predict=700,
    )

    return json.loads(refined)

def main() -> None:
    try:
        config = load_yaml("app/config.yaml")

        if len(sys.argv) < 2:
            print("用法: python3 app/review_scene.py <scene_draft_path>")
            sys.exit(1)

        draft_rel_path = sys.argv[1]
        draft_text = clip_text(read_text(draft_rel_path), 3000)

        task_text = clip_text(read_text("01_inputs/tasks/current_task.md"), 2200)
        task_id = extract_markdown_field(task_text, "task_id") or "unknown-task"

        chapter_state_path = extract_markdown_field(task_text, "chapter_state")
        if chapter_state_path:
            chapter_state = clip_text(read_text(chapter_state_path), 2200)
        else:
            chapter_state = "[未提供 chapter_state]"

        based_on_path = extract_markdown_field(task_text, "based_on")
        if based_on_path:
            based_on_text = clip_text(read_text(based_on_path), 2200)
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

        raw_output = call_ollama(
            model=config["reviewer"]["model"],
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            base_url=config["reviewer"]["base_url"],
            num_ctx=config["reviewer"]["num_ctx"],
            temperature=0.1,
            timeout=config["reviewer"]["request_timeout"],
            num_predict=900,
        )

        try:
            result = json.loads(raw_output)
        except Exception:
            print("Reviewer 原始输出如下：")
            print("=" * 40)
            print(raw_output)
            print("=" * 40)
            print("Reviewer 未直接输出 JSON，正在尝试提纯为 JSON...")
            result = extract_reviewer_json(config, task_id, raw_output)
        validate(instance=result, schema=schema)

        # task_id 对齐
        result["task_id"] = task_id

        out_path = f"02_working/reviews/{task_id}_reviewer.json"
        save_text(out_path, json.dumps(result, ensure_ascii=False, indent=2))

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