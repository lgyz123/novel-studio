import json
import re
from pathlib import Path
from typing import Any

import requests
import yaml
from jsonschema import validate


ROOT = Path(__file__).resolve().parent.parent


def read_text(rel_path: str) -> str:
    path = ROOT / rel_path
    return path.read_text(encoding="utf-8")


def load_yaml(rel_path: str) -> dict:
    path = ROOT / rel_path
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_text(rel_path: str, content: str) -> None:
    path = ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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

    print(f"正在请求 Ollama: {model} @ {base_url}")
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()

    return response.json()


def extract_message_text(response_data: dict) -> str:
    message = response_data.get("message", {})
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    for key in ("response", "content", "thinking", "reasoning"):
        value = response_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def extract_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    if not text:
        raise ValueError("模型没有输出内容")

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
        raise ValueError("模型没有输出合法 JSON")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError("模型没有输出合法 JSON") from exc


def contains_forbidden_modern_terms(text: str) -> list[str]:
    forbidden_terms = [
        "便利店",
        "收银机",
        "霓虹灯",
        "玻璃橱窗",
        "数据",
        "格式化",
        "档案室",
        "运尸车",
    ]
    return [term for term in forbidden_terms if term in text]


def compile_context(config: dict) -> str:
    task_text = clip_text(read_text("01_inputs/tasks/current_task.md"), 1200)
    novel_manifest = clip_text(read_text("00_manifest/novel_manifest.md"), 1500)
    world_bible = clip_text(read_text("00_manifest/world_bible.md"), 1200)
    character_bible = clip_text(read_text("00_manifest/character_bible.md"), 1200)
    life_notes = clip_text(read_text("01_inputs/life_notes/latest.md"), 800)

    compiled = f"""# 当前任务
{task_text}

# 本次必须遵守的项目总纲
{novel_manifest}

# 本次相关世界设定
{world_bible}

# 本次相关人物设定
{character_bible}

# 本次生活素材使用规则
- 生活素材只能提取气氛、感官、情绪、节奏、意象
- 禁止直接搬运现代现实世界的具体物件或设施进入小说场景
- 如与小说世界冲突，必须优先服从小说设定

# 本次可借用的生活素材
{life_notes}
"""

    context_file = config["output"]["context_file"]
    save_text(context_file, compiled)
    return compiled


def parse_markdown_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            current_key = line[2:].strip().lower()
            sections[current_key] = []
            continue

        if current_key is not None:
            sections[current_key].append(line)

    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def build_decision_json(config: dict, current_context: str) -> dict:
    schema = json.loads(read_text("prompts/output_schema.json"))
    task_text = read_text("01_inputs/tasks/current_task.md")
    sections = parse_markdown_sections(task_text)

    task_id = sections.get("task_id", "").strip() or "draft-task"
    goal = sections.get("goal", "").strip() or "根据当前设定生成草稿"
    draft_file = sections.get("output_target", "").strip()

    if not draft_file:
        draft_file = f"{config['output']['draft_dir']}/{task_id}.md"

    if not draft_file.startswith("02_working/drafts/"):
        raise ValueError("output_target 非法，必须写入 02_working/drafts/")

    risks = [
        "当前草稿依赖摘要化上下文，可能遗漏设定书中的细小约束。",
        "若任务单未明确点名角色或冲突边界，草稿需要人工复核其是否越界。",
    ]

    constraints = sections.get("constraints", "")
    if "不展开完整世界观" in constraints:
        risks.append("本次任务要求压缩世界观信息，可能导致背景信息呈现偏克制。")

    result = {
        "task_id": task_id,
        "goal": goal,
        "used_sources": [
            "01_inputs/tasks/current_task.md",
            config["output"]["context_file"],
        ],
        "risks": risks[:3],
        "next_action": "human_review",
        "draft_file": draft_file,
    }

    validate(instance=result, schema=schema)
    return result


def generate_markdown_draft(config: dict, current_context: str, decision: dict) -> str:
    system_prompt = read_text("prompts/writer_system.md")
    task_text = read_text("01_inputs/tasks/current_task.md")

    user_prompt = f"""请根据以下输入写出 Markdown 草稿正文。

要求：
1. 只输出 Markdown 正文
2. 不要输出 JSON
3. 不要输出 [JSON]
4. 不要输出 [MARKDOWN]
5. 不要写解释
6. 正文控制在任务要求范围内

【任务单】
{task_text}

【当前上下文】
{current_context}

【决策信息】
{json.dumps(decision, ensure_ascii=False, indent=2)}
"""

    print("正在请求模型生成草稿，请稍候...")
    markdown_response = call_ollama(
        model=config["agent"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["agent"]["base_url"],
        num_ctx=config["generation"]["write_num_ctx"],
        temperature=config["generation"]["temperature"],
        timeout=config["generation"]["request_timeout"],
        num_predict=700,
    )
    markdown_text = extract_message_text(markdown_response)

    if not markdown_text.strip():
        raise ValueError("模型没有输出草稿正文")

    forbidden_found = contains_forbidden_modern_terms(markdown_text)
    if forbidden_found:
        raise ValueError(f"草稿包含不允许的现代词汇: {forbidden_found}")

    return markdown_text.strip()


def write_draft(config: dict, current_context: str) -> None:
    decision = build_decision_json(config, current_context)
    markdown_text = generate_markdown_draft(config, current_context, decision)

    decision_file = f"02_working/reviews/{decision['task_id']}.json"
    draft_file = decision["draft_file"]

    save_text(decision_file, json.dumps(decision, ensure_ascii=False, indent=2))
    save_text(draft_file, markdown_text)

    print(f"已保存决策文件: {decision_file}")
    print(f"已保存草稿文件: {draft_file}")


def main() -> None:
    try:
        config = load_yaml("app/config.yaml")

        print("步骤 1/2：正在整理当前上下文...")
        current_context = compile_context(config)
        print(f"已生成上下文文件: {config['output']['context_file']}")

        print("步骤 2/2：正在生成草稿...")
        write_draft(config, current_context)

        print("本次任务完成，下一步请人工审阅。")

    except FileNotFoundError as e:
        print(f"缺少输入文件: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
    except requests.exceptions.ReadTimeout:
        print("运行失败: 请求模型超时。请缩短任务输入，或提高 request_timeout。")
    except Exception as e:
        print(f"运行失败: {e}")


if __name__ == "__main__":
    main()