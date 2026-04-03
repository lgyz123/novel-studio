import json
from pathlib import Path

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


def call_ollama(model: str, system_prompt: str, user_prompt: str, base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False
    }

    response = requests.post(url, json=payload, timeout=180)
    response.raise_for_status()

    data = response.json()
    return data["message"]["content"]


def split_response(text: str) -> tuple[str, str]:
    if "[JSON]" not in text or "[MARKDOWN]" not in text:
        raise ValueError("模型输出缺少 [JSON] 或 [MARKDOWN] 标记")

    json_part = text.split("[JSON]", 1)[1].split("[MARKDOWN]", 1)[0].strip()
    markdown_part = text.split("[MARKDOWN]", 1)[1].strip()

    if not json_part:
        raise ValueError("JSON 部分为空")
    if not markdown_part:
        raise ValueError("Markdown 部分为空")

    return json_part, markdown_part


def build_user_prompt(
    task_text: str,
    novel_manifest: str,
    world_bible: str,
    character_bible: str,
    life_notes: str,
) -> str:
    return f"""请根据以下输入完成写作任务。

【任务单】
{task_text}

【小说总纲】
{novel_manifest}

【世界观】
{world_bible}

【人物设定】
{character_bible}

【最近生活素材】
{life_notes}

请严格遵守系统规则，并严格输出以下两个部分：

[JSON]
请输出一个合法 JSON 对象，字段必须符合既定要求。

[MARKDOWN]
请输出可直接保存成草稿文件的 Markdown 正文。
"""


def main() -> None:
    try:
        config = load_yaml("app/config.yaml")

        system_prompt = read_text("prompts/writer_system.md")
        schema = json.loads(read_text("prompts/output_schema.json"))

        task_text = read_text("01_inputs/tasks/current_task.md")
        novel_manifest = read_text("00_manifest/novel_manifest.md")
        world_bible = read_text("00_manifest/world_bible.md")
        character_bible = read_text("00_manifest/character_bible.md")
        life_notes = read_text("01_inputs/life_notes/latest.md")

        user_prompt = build_user_prompt(
            task_text=task_text,
            novel_manifest=novel_manifest,
            world_bible=world_bible,
            character_bible=character_bible,
            life_notes=life_notes,
        )

        model_name = config["agent"]["model"]
        ollama_base_url = config["agent"]["base_url"]

        raw_output = call_ollama(
            model=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            base_url=ollama_base_url,
        )

        json_text, markdown_text = split_response(raw_output)
        result = json.loads(json_text)

        validate(instance=result, schema=schema)

        draft_file = result["draft_file"]
        if not draft_file.startswith("02_working/drafts/"):
            raise ValueError("draft_file 非法，禁止写入非 working 区域")

        decision_file = f"02_working/reviews/{result['task_id']}.json"

        save_text(decision_file, json.dumps(result, ensure_ascii=False, indent=2))
        save_text(draft_file, markdown_text)

        print(f"已保存决策文件: {decision_file}")
        print(f"已保存草稿文件: {draft_file}")
        print("本次任务完成，下一步请人工审阅。")

    except FileNotFoundError as e:
        print(f"缺少输入文件: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
    except Exception as e:
        print(f"运行失败: {e}")


if __name__ == "__main__":
    main()