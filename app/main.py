import json
import re
from pathlib import Path

import requests
import yaml
from issue_filters import filter_shared_issues
from jsonschema import validate
from review_scene import review_scene_file


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

    print(f"正在请求 Ollama: {model} @ {base_url}")
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()

    data = response.json()
    return data["message"]["content"]


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
        "红绿灯",
        "马路",
        "路灯",
        "出租车",
        "手机",
        "电梯",
        "监控",
    ]
    return [term for term in forbidden_terms if term in text]


def extract_markdown_field(task_text: str, field_name: str) -> str | None:
    pattern = rf"(?ms)^#\s*{re.escape(field_name)}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, task_text)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


def contains_script_style(text: str) -> list[str]:
    problems = []

    # 1. 明确的“场景说明”式写法
    if re.search(r"[（(]\s*场景\s*[:：]", text):
        problems.append("出现“（场景：...）”式舞台说明")

    # 2. 明确的人名加冒号台词格式
    dialogue_lines = re.findall(r"(?m)^\s*[一-龥A-Za-z0-9_]{1,12}[:：]", text)
    if len(dialogue_lines) >= 2:
        problems.append("出现多行“人物名：对白”格式")

    # 3. 连续两行及以上纯括号舞台说明
    pure_parenthetical_lines = re.findall(r"(?m)^\s*[（(].*[)）]\s*$", text)
    if len(pure_parenthetical_lines) >= 2:
        problems.append("出现连续括号舞台说明")

    return problems


def is_likely_truncated(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False

    suspicious_endings = [
        "（",
        "(",
        "“",
        "\"",
        "：",
        ":",
        "——",
        "…",
        "「",
        "『",
        "，",
        ",",
    ]
    if any(stripped.endswith(x) for x in suspicious_endings):
        return True

    # 末尾如果明显像半截句，也算可疑
    if len(stripped) >= 1 and stripped[-1].isalnum():
        # 中文正文末尾没有句号不一定错，但结合长度太短时可疑
        if len(stripped) < 80:
            return True

    return False


def extract_forbidden_characters(task_text: str) -> list[str]:
    constraints = extract_markdown_field(task_text, "constraints") or ""
    blocked = []

    known_names = [
        "谢观鱼",
        "裴照骨",
        "净苦和尚",
        "阿绣",
    ]

    for name in known_names:
        patterns = [
            f"不要让{name}出场",
            f"不允许{name}出场",
            f"本场景不要让{name}出场",
            f"不要{name}出场",
        ]
        if any(p in constraints for p in patterns):
            blocked.append(name)

    return blocked


def detect_forbidden_characters(task_text: str, draft_text: str) -> list[str]:
    blocked = extract_forbidden_characters(task_text)
    return [name for name in blocked if name in draft_text]

def contains_editorial_explanation(text: str) -> list[str]:
    markers = [
        "【修订说明】",
        "【修改说明】",
        "【说明】",
        "以下为",
        "改写说明",
        "修订说明",
        "注：",
    ]
    return [m for m in markers if m in text]


def build_validation_errors(task_text: str, draft_text: str) -> list[str]:
    errors = []

    modern_terms = contains_forbidden_modern_terms(draft_text)
    editorial_markers = contains_editorial_explanation(draft_text)
    if editorial_markers:
        errors.append(f"包含说明性附加文本，不属于小说正文: {editorial_markers}")
    if modern_terms:
        errors.append(f"包含不允许的现代词汇: {modern_terms}")

    script_style = contains_script_style(draft_text)
    if script_style:
        errors.append("文本呈现剧本体/分镜体痕迹，不符合小说正文要求")

    forbidden_characters = detect_forbidden_characters(task_text, draft_text)
    if forbidden_characters:
        errors.append(f"违反角色边界限制，出现了不应出场人物: {forbidden_characters}")

    if is_likely_truncated(draft_text):
        errors.append("草稿疑似被截断或结尾不完整")

    return errors

def build_relevant_character_section(task_text: str, character_bible: str) -> str:
    constraints = extract_markdown_field(task_text, "constraints") or ""

    allowed_names = ["孟浮灯"]
    if "老张头可以" in constraints or "老张头" in constraints:
        allowed_names.append("老张头")

    sections = []
    for name in allowed_names:
        pattern = rf"(?ms)^###\s*{re.escape(name)}\s*\n(.*?)(?=^###\s|\Z)"
        match = re.search(pattern, character_bible)
        if match:
            sections.append(f"### {name}\n{match.group(1).strip()}")

    if sections:
        return "\n\n".join(sections)

    # 如果没匹配到结构化人物段，就退化为短提示
    return "### 当前相关人物\n- 孟浮灯：本场核心视角人物\n- 老张头：可极轻出场的背景人物"

def compile_context(config: dict) -> str:
    task_text = clip_text(read_text("01_inputs/tasks/current_task.md"), 1600)
    novel_manifest = clip_text(read_text("00_manifest/novel_manifest.md"), 900)
    world_bible = clip_text(read_text("00_manifest/world_bible.md"), 700)
    character_bible_full = read_text("00_manifest/character_bible.md")
    relevant_characters = build_relevant_character_section(task_text, character_bible_full)
    character_bible = clip_text(read_text("00_manifest/character_bible.md"), 700)
    life_notes = clip_text(read_text("01_inputs/life_notes/latest.md"), 800)

    based_on_path = extract_markdown_field(task_text, "based_on")
    based_on_section = ""

    if based_on_path:
        based_on_path = based_on_path.strip()
        try:
            based_on_text = clip_text(read_text(based_on_path), 1600)
            based_on_section = f"""

# 本次修订所依据的旧稿
来源文件：{based_on_path}

{based_on_text}
"""
        except FileNotFoundError:
            based_on_section = f"""

# 本次修订所依据的旧稿
来源文件：{based_on_path}

[警告：未找到该文件，无法载入旧稿内容]
"""

    chapter_state_path = extract_markdown_field(task_text, "chapter_state")
    chapter_state_section = ""

    if chapter_state_path:
        chapter_state_path = chapter_state_path.strip()
        try:
            chapter_state_text = clip_text(read_text(chapter_state_path), 1600)
            chapter_state_section = f"""

# 当前章节状态
来源文件：{chapter_state_path}

{chapter_state_text}
"""
        except FileNotFoundError:
            chapter_state_section = f"""

# 当前章节状态
来源文件：{chapter_state_path}

[警告：未找到该文件，无法载入章节状态]
"""

    compiled = f"""# 当前任务
{task_text}

# 本次必须遵守的项目总纲
{novel_manifest}

# 本次相关世界设定
{world_bible}

# 本次相关人物设定
{relevant_characters}

# 本次生活素材使用规则
- 生活素材只能提取气氛、感官、情绪、节奏、意象
- 禁止直接搬运现代现实世界的具体物件或设施进入小说场景
- 如与小说世界冲突，必须优先服从小说设定

# 本次可借用的生活素材
{life_notes}{based_on_section}{chapter_state_section}
"""

    context_file = config["output"]["context_file"]
    save_text(context_file, compiled)
    return compiled


def generate_decision_json(config: dict, current_context: str) -> dict:
    schema = json.loads(read_text("prompts/output_schema.json"))
    task_text = read_text("01_inputs/tasks/current_task.md")
    task_id = extract_markdown_field(task_text, "task_id") or "draft-task"
    goal = extract_markdown_field(task_text, "goal") or "根据当前设定生成草稿"
    draft_file = extract_markdown_field(task_text, "output_target")
    based_on_path = extract_markdown_field(task_text, "based_on")

    if not draft_file:
        draft_dir = config["output"]["draft_dir"]
        draft_file = f"{draft_dir}/{task_id}.md"

    if not draft_file.startswith("02_working/drafts/"):
        raise ValueError("draft_file 非法，禁止写入非 working 区域")

    used_sources = [
        "01_inputs/tasks/current_task.md",
        config["output"]["context_file"],
    ]
    if based_on_path:
        used_sources.append(based_on_path)

    risks = [
        "当前草稿依赖整理后的上下文，可能遗漏设定书中的局部细节。",
        "若任务单未明确角色边界或场景目标，草稿需要人工复核是否越界。",
    ]

    constraints = extract_markdown_field(task_text, "constraints") or ""
    if "不展开完整世界观" in constraints:
        risks.append("本次任务限制世界观展开，草稿可能有意保持信息密度克制。")
    elif "不新增重要设定" in constraints or "不新增制度性设定" in constraints:
        risks.append("本次任务限制新增设定，草稿需要人工检查是否有偷渡设定的句子。")

    result = {
        "task_id": task_id,
        "goal": goal,
        "used_sources": used_sources,
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
7. 必须是小说正文 prose，不允许写成剧本、分镜、舞台说明
8. 如果任务限制了人物出场边界，必须严格服从
9. 如果任务要求不新增设定，就不要擅自发明制度规则或主线钩子
10. 不要写“以下为……”
11. 不要写“注：……”
12. 不要附带创作说明、改写说明、风格说明
13. 不要使用括号包裹整段说明文字
【任务单】
{task_text}

【当前上下文】
{current_context}

【决策信息】
{json.dumps(decision, ensure_ascii=False, indent=2)}
"""

    print("正在请求模型生成草稿，请稍候...")
    markdown_text = call_ollama(
        model=config["writer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["writer"]["base_url"],
        num_ctx=config["generation"]["write_num_ctx"],
        temperature=config["generation"]["temperature"],
        timeout=config["generation"]["request_timeout"],
        num_predict=1000,
    )

    # return markdown_text.strip()
    return clean_model_output(markdown_text)

def rewrite_script_to_prose(config: dict, current_context: str, bad_draft: str) -> str:
    system_prompt = """你是小说改写助手。
你的任务是把一段剧本体、分镜体或舞台说明式文字，改写为连续的小说正文 prose。
不要新增设定，不要新增角色，不要改变原场景的基本事件顺序。
只输出改写后的小说正文，不要解释。"""

    task_text = read_text("01_inputs/tasks/current_task.md")

    user_prompt = f"""请把下面这段文本改写成小说正文 prose。

要求：
1. 去掉标题
2. 去掉括号场景说明
3. 去掉“人物名：”格式
4. 改写成连续叙事段落
5. 不新增角色
6. 不新增制度设定
7. 不新增主线钩子
8. 保持任务约束
9. 只输出改写后的正文

【任务单】
{task_text}

【当前上下文】
{current_context}

【待改写文本】
{bad_draft}
"""

    print("检测到剧本体，正在尝试自动改写为小说正文...")
    rewritten = call_ollama(
        model=config["writer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["writer"]["base_url"],
        num_ctx=config["generation"]["write_num_ctx"],
        temperature=0.2,
        timeout=config["generation"]["request_timeout"],
        num_predict=1200,
    )

    # return rewritten.strip()
    return clean_model_output(rewritten)

def extract_plain_prose(config: dict, current_context: str, bad_draft: str) -> str:
    system_prompt = """你是小说正文提纯助手。
你的任务不是重写剧情，而是从输入文本中提取可用的小说正文 prose。
删除标题、括号说明、人物名加冒号的台词格式、修订说明、注释、解释文字。
保留叙述段落，不新增设定，不新增角色，不改变原有事件顺序。
只输出提纯后的小说正文。"""

    task_text = read_text("01_inputs/tasks/current_task.md")

    user_prompt = f"""请把下面文本提纯为小说正文 prose。

要求：
1. 只保留小说正文段落
2. 删除标题
3. 删除括号场景说明
4. 删除“人物名：对白”格式
5. 删除修订说明、注释、解释文字
6. 不新增角色
7. 不新增设定
8. 不改变事件顺序
9. 只输出提纯后的正文

【任务单】
{task_text}

【当前上下文】
{current_context}

【待提纯文本】
{bad_draft}
"""

    print("改写仍失败，正在尝试提纯为纯正文...")
    refined = call_ollama(
        model=config["writer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["writer"]["base_url"],
        num_ctx=config["generation"]["write_num_ctx"],
        temperature=0.1,
        timeout=config["generation"]["request_timeout"],
        num_predict=1200,
    )

    return clean_model_output(refined)

def save_failed_draft(task_id: str, content: str, suffix: str = "failed") -> None:
    path = f"02_working/logs/{task_id}_{suffix}.md"
    save_text(path, content)
    print(f"已保存失败稿供检查: {path}")

def validate_draft(task_text: str, draft_text: str) -> None:
    errors = build_validation_errors(task_text, draft_text)
    if errors:
        joined = "；".join(errors)
        raise ValueError(f"草稿验收失败: {joined}")


def strip_standalone_stage_directions(text: str) -> str:
    lines = text.splitlines()
    cleaned_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if re.fullmatch(r"[（(][^\n]{0,200}[)）]", stripped):
            continue
        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
    return cleaned_text.strip()


def write_draft(config: dict, current_context: str) -> dict:
    task_text = read_text("01_inputs/tasks/current_task.md")
    decision = generate_decision_json(config, current_context)
    task_id = decision["task_id"]

    markdown_text = generate_markdown_draft(config, current_context, decision)

    errors = build_validation_errors(task_text, markdown_text)
    errors = build_validation_errors(task_text, markdown_text)
    if errors:
        save_failed_draft(task_id, markdown_text, "first_failed")
        save_failure_reason(task_id, "；".join(errors), "first_failed_reason")

        # 先处理纯说明性污染
        if all("说明性附加文本" in e for e in errors):
            markdown_text = clean_model_output(markdown_text)
            errors = build_validation_errors(task_text, markdown_text)

        # 第一层 fallback：剧本体 -> prose 改写
        if errors and any("剧本体" in e or "分镜体" in e for e in errors):
            rewritten = rewrite_script_to_prose(config, current_context, markdown_text)
            save_failed_draft(task_id, rewritten, "rewritten_attempt")

            rewritten_errors = build_validation_errors(task_text, rewritten)
            if not rewritten_errors:
                markdown_text = rewritten
            else:
                save_failure_reason(task_id, "；".join(rewritten_errors), "rewritten_failed_reason")

                # 第二层 fallback：提纯正文
                refined = extract_plain_prose(config, current_context, rewritten)
                save_failed_draft(task_id, refined, "refined_attempt")

                refined_errors = build_validation_errors(task_text, refined)
                if refined_errors:
                    save_failure_reason(task_id, "；".join(refined_errors), "refined_failed_reason")
                    print("提纯后验收失败，具体原因如下：")
                    for err in refined_errors:
                        print(f"- {err}")
                    raise ValueError(f"草稿验收失败（提纯后仍不通过）: {'；'.join(refined_errors)}")

                markdown_text = refined

        elif errors:
            raise ValueError(f"草稿验收失败: {'；'.join(errors)}")

    decision_file = f"02_working/reviews/{decision['task_id']}.json"
    draft_file = decision["draft_file"]

    save_text(decision_file, json.dumps(decision, ensure_ascii=False, indent=2))
    save_text(draft_file, markdown_text)

    print(f"已保存决策文件: {decision_file}")
    print(f"已保存草稿文件: {draft_file}")
    return {
        "task_text": task_text,
        "decision": decision,
        "decision_file": decision_file,
        "draft_file": draft_file,
    }

def clean_model_output(text: str) -> str:
    text = text.strip()

    # 删除开头常见说明行
    patterns_to_remove = [
        r"^（以下为.*?）\s*",
        r"^\(以下为.*?\)\s*",
        r"^以下为.*?\n",
        r"^Rewritten\s*[:：]?\s*",
        r"^改写后[:：]?\s*",
        r"^修订版[:：]?\s*",
        r"^\*\*.*?修订版.*?\*\*\s*",
        r"^【修订后场景】\s*",
        r"^【场景修订版】\s*",
        r"^【正文】\s*",
    ]

    for pattern in patterns_to_remove:
        text = re.sub(pattern, "", text, flags=re.MULTILINE)

    # 遇到说明性标记，直接截断后面全部内容
    split_markers = [
        "【修订说明】",
        "【修改说明】",
        "【说明】",
        "\n注：",
        "\n（注：",
        "\n(注：",
    ]

    cut_positions = [text.find(marker) for marker in split_markers if text.find(marker) != -1]
    if cut_positions:
        text = text[:min(cut_positions)]

    text = strip_standalone_stage_directions(text)

    return text.strip()

def save_failure_reason(task_id: str, reason: str, suffix: str = "failure_reason") -> None:
    path = f"02_working/logs/{task_id}_{suffix}.txt"
    save_text(path, reason)
    print(f"已保存失败原因: {path}")


def normalize_issue_lines(issues: list[str]) -> list[str]:
    cleaned = []
    for item in issues:
        text = str(item).strip()
        if not text:
            continue
        cleaned.append(text)
    return cleaned


def get_filtered_reviewer_issues(reviewer_result: dict, task_text: str) -> tuple[list[str], list[str]]:
    major_issues = filter_shared_issues(list(reviewer_result.get("major_issues", [])), task_text=task_text)
    minor_issues = filter_shared_issues(list(reviewer_result.get("minor_issues", [])), task_text=task_text)
    return major_issues, minor_issues


def strip_revision_prefix(goal: str) -> str:
    prefixes = [
        "基于上一版草稿进行小修：",
        "基于上一版草稿进行重写：",
        "对上一版草稿进行小修：",
        "对上一版草稿进行重写：",
    ]
    cleaned = goal.strip()
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True
    return cleaned


def is_problem_like_issue(text: str) -> bool:
    text = str(text).strip()
    if not text:
        return False

    problem_markers = [
        "未完成",
        "不足",
        "不够",
        "偏弱",
        "偏空",
        "过满",
        "越界",
        "失衡",
        "过多",
        "不明确",
        "不清晰",
        "未能",
        "没有形成",
        "不充分",
        "缺少",
        "缺乏",
        "太满",
        "太散",
        "太重",
        "太轻",
        "闭环感弱",
        "闭环偏弱",
        "牵引力不够",
        "动作牵引不够",
    ]
    pure_constraint_markers = [
        "No new characters",
        "保持单视角",
        "不引入新人物",
        "不新增制度性设定",
        "只允许孟浮灯作为核心视角人物",
        "不引入谢观鱼",
        "不引入裴照骨",
        "不引入净苦和尚",
    ]

    if any(marker in text for marker in pure_constraint_markers):
        return False

    return any(marker in text for marker in problem_markers)


def filter_followup_issue_lines(issues: list[str]) -> list[str]:
    return [text for text in normalize_issue_lines(issues) if is_problem_like_issue(text)]


def filter_usable_issues(issues: list[str]) -> list[str]:
    bad_exact = {
        "No new characters.",
        "No new characters",
        "不引入新人物。",
        "不新增制度性设定。",
        "保持单视角。",
    }

    cleaned = []
    for issue in issues:
        text = str(issue).strip()
        if not text:
            continue
        if text in bad_exact:
            continue
        if "No new characters" in text:
            continue
        if "Must not" in text or "The task:" in text:
            continue
        if "We need to check" in text or "But maybe" in text or "So maybe" in text:
            continue
        cleaned.append(text)
    return cleaned


def normalize_constraint_text(text: str) -> str:
    text = str(text).strip()
    text = re.sub(r"^[#\-\*\d\.\s]+", "", text)
    text = re.sub(r"[：:；;，,。.!！?？\s]+", "", text)
    return text


def dedupe_followup_issue_lines(original_constraints: str, issue_lines: list[str]) -> list[str]:
    original_lines = [
        normalize_constraint_text(line)
        for line in original_constraints.splitlines()
        if line.strip()
    ]

    deduped: list[str] = []
    seen_normalized: set[str] = set()

    for issue in issue_lines:
        normalized_issue = normalize_constraint_text(issue)
        if not normalized_issue:
            continue
        if normalized_issue in seen_normalized:
            continue
        if any(
            normalized_issue == original
            or normalized_issue in original
            or original in normalized_issue
            for original in original_lines
            if original
        ):
            continue
        deduped.append(issue)
        seen_normalized.add(normalized_issue)

    return deduped


def build_followup_task_id(task_id: str, mode: str) -> str:
    base = re.sub(r"-R\d+$", "", task_id)
    match = re.search(r"-R(\d+)$", task_id)
    if mode == "revise":
        if match:
            next_number = int(match.group(1)) + 1
        else:
            next_number = 1
        return f"{base}-R{next_number}"
    if mode == "rewrite":
        return f"{base}-RW1"
    return f"{base}-R1"


def build_followup_output_target(draft_file: str, mode: str) -> str:
    path = Path(draft_file)
    stem = path.stem

    if mode == "rewrite":
        rewrite_match = re.search(r"^(.*?)(_rewrite(?:\d+)?)$", stem)
        if rewrite_match:
            base_stem = rewrite_match.group(1)
            suffix = rewrite_match.group(2)
            number_match = re.search(r"_rewrite(\d+)$", suffix)
            if number_match:
                next_number = int(number_match.group(1)) + 1
                stem = f"{base_stem}_rewrite{next_number}"
            else:
                stem = f"{base_stem}_rewrite2"
        else:
            stem = f"{stem}_rewrite"
    else:
        version_matches = re.findall(r"_v(\d+)", stem)
        if version_matches:
            base_stem = re.sub(r"(?:_v\d+)+$", "", stem)
            next_version = int(version_matches[-1]) + 1
            stem = f"{base_stem}_v{next_version}"
        else:
            stem = f"{stem}_v2"

    return path.with_name(f"{stem}{path.suffix}").as_posix()


def build_followup_goal(original_goal: str, reviewer_result: dict, mode: str, task_text: str) -> str:
    base_goal = strip_revision_prefix(original_goal)
    summary = str(reviewer_result.get("summary", "")).strip()
    filtered_major, filtered_minor = get_filtered_reviewer_issues(reviewer_result, task_text)
    major_issues = filter_usable_issues(filtered_major)
    minor_issues = filter_usable_issues(filtered_minor)
    issues = filter_followup_issue_lines(
        major_issues + minor_issues
    )

    prefix = "基于上一版草稿进行小修" if mode == "revise" else "基于上一版草稿重新写作"

    normalized_summary = normalize_constraint_text(summary)
    deduped_issues = []
    for issue in issues[:3]:
        normalized_issue = normalize_constraint_text(issue)
        if normalized_summary and normalized_issue:
            if (
                normalized_issue == normalized_summary
                or normalized_issue in normalized_summary
                or normalized_summary in normalized_issue
            ):
                continue
        deduped_issues.append(issue)

    issue_text = "；".join(deduped_issues) if deduped_issues else summary
    if issue_text:
        return f"{prefix}：{base_goal}。本次重点解决：{issue_text}"
    return f"{prefix}：{base_goal}。"


def build_followup_constraints(task_text: str, reviewer_result: dict) -> str:
    original_constraints = (extract_markdown_field(task_text, "constraints") or "").strip()
    filtered_major, filtered_minor = get_filtered_reviewer_issues(reviewer_result, task_text)
    major_issues = filter_usable_issues(filtered_major)
    minor_issues = filter_usable_issues(filtered_minor)
    issue_lines = filter_followup_issue_lines(
        major_issues + minor_issues
    )
    issue_lines = dedupe_followup_issue_lines(original_constraints, issue_lines)

    blocks = []
    if original_constraints:
        blocks.append(original_constraints)

    if issue_lines:
        blocks.append("- 额外修订要求：")
        blocks.extend([f"- {line}" for line in issue_lines])
    else:
        summary = str(reviewer_result.get("summary", "")).strip()
        if summary:
            blocks.append(f"- 额外修订要求：{summary}")

    return "\n".join(blocks).strip()


def build_generated_task_content(task_text: str, reviewer_result: dict, draft_file: str, mode: str) -> str:
    task_id = extract_markdown_field(task_text, "task_id") or "generated-task"
    original_goal = extract_markdown_field(task_text, "goal") or "根据 reviewer 结果继续处理当前草稿"
    chapter_state = extract_markdown_field(task_text, "chapter_state")
    preferred_length = extract_markdown_field(task_text, "preferred_length")

    new_task_id = build_followup_task_id(task_id, mode)
    new_goal = build_followup_goal(original_goal, reviewer_result, mode, task_text)
    new_constraints = build_followup_constraints(task_text, reviewer_result)
    new_output_target = build_followup_output_target(draft_file, mode)

    sections = [
        f"# task_id\n{new_task_id}",
        f"# goal\n{new_goal}",
        f"# based_on\n{draft_file}",
    ]

    if chapter_state:
        sections.append(f"# chapter_state\n{chapter_state}")

    sections.append(f"# constraints\n{new_constraints}")

    if preferred_length:
        sections.append(f"# preferred_length\n{preferred_length}")

    sections.append(f"# output_target\n{new_output_target}")
    return "\n\n".join(sections) + "\n"


def build_locked_chapter_file(draft_file: str, locked_dir: str) -> str:
    path = Path(draft_file)
    stem = path.stem
    stem = re.sub(r"(?:_v\d+)+$", "", stem)
    stem = re.sub(r"_rewrite\d*$", "", stem)
    return f"{locked_dir}/chapters/{stem}{path.suffix}"


def extract_revision_count(task_id: str) -> int:
    match = re.search(r"-R(\d+)$", task_id)
    if not match:
        return 0
    return int(match.group(1))


def build_locked_notes_content(task_text: str, reviewer_result: dict, draft_file: str, locked_file: str) -> str:
    task_id = extract_markdown_field(task_text, "task_id") or "today"
    lock_date = task_id[:10] if re.match(r"\d{4}-\d{2}-\d{2}", task_id[:10]) else "today"
    goal = extract_markdown_field(task_text, "goal") or "本场景功能待补充"
    minor_issues = normalize_issue_lines(list(reviewer_result.get("minor_issues", [])))
    stem = Path(locked_file).stem

    lines = [
        f"# {stem} 锁定说明",
        "",
        f"- 锁定日期：{lock_date}",
        f"- 正文文件：{locked_file}",
        f"- 来源草稿：{draft_file}",
        f"- reviewer verdict：{reviewer_result.get('verdict', 'lock')}",
        f"- reviewer summary：{str(reviewer_result.get('summary', '')).strip()}",
        "",
        "## 本场景功能",
        f"- {goal}",
    ]

    if minor_issues:
        lines.extend(["", "## 后续留意"])
        lines.extend([f"- {item}" for item in minor_issues])

    return "\n".join(lines).strip() + "\n"


def build_working_notes_proposal_content(task_text: str, reviewer_result: dict, draft_file: str, locked_file: str, notes_file: str) -> str:
    goal = extract_markdown_field(task_text, "goal") or "本场景功能待补充"
    minor_issues = normalize_issue_lines(list(reviewer_result.get("minor_issues", [])))
    lines = [
        f"# {Path(locked_file).stem} canon notes 更新提议",
        "",
        f"- 建议同步到：{notes_file}",
        f"- 对应 locked 正文：{locked_file}",
        f"- 来源草稿：{draft_file}",
        f"- reviewer summary：{str(reviewer_result.get('summary', '')).strip()}",
        "",
        "## 建议保留的场景功能",
        f"- {goal}",
    ]

    if minor_issues:
        lines.extend(["", "## 可写入 notes 的后续留意"])
        lines.extend([f"- {item}" for item in minor_issues])

    return "\n".join(lines).strip() + "\n"


def build_working_state_proposal_content(task_text: str, reviewer_result: dict, locked_file: str, chapter_state_path: str | None) -> str:
    goal = extract_markdown_field(task_text, "goal") or "本场景功能待补充"
    summary = str(reviewer_result.get("summary", "")).strip()
    stem = Path(locked_file).stem
    lines = [
        f"# {stem} 对 ch01_state 的更新提议",
        "",
        f"- 建议同步到：{chapter_state_path or '03_locked/canon/ch01_state.md'}",
        f"- 对应 locked 正文：{locked_file}",
        "",
        "## 建议补入“已锁定场景”",
        f"- {stem}：{goal}",
        "",
        "## 建议补入“当前主角状态 / 已锁定线索”",
        f"- {summary or '本场景已完成锁定，可根据正文补充主角状态与线索推进。'}",
        "",
        "## 建议人工确认",
        "- 是否需要把本场新增的动作偏移写入主角状态",
        "- 是否需要把本场确认的低烈度推进写入章节节奏判断",
    ]
    return "\n".join(lines).strip() + "\n"


def build_manual_intervention_content(task_text: str, reviewer_result: dict, draft_file: str, max_revisions: int) -> str:
    task_id = extract_markdown_field(task_text, "task_id") or "unknown-task"
    summary = str(reviewer_result.get("summary", "")).strip()
    major_issues = normalize_issue_lines(list(reviewer_result.get("major_issues", [])))
    minor_issues = normalize_issue_lines(list(reviewer_result.get("minor_issues", [])))

    lines = [
        f"# {task_id} 人工介入提醒",
        "",
        f"- 已达到最大自动修订次数：{max_revisions}",
        f"- 当前草稿：{draft_file}",
        f"- reviewer verdict：{reviewer_result.get('verdict', 'revise')}",
        f"- reviewer summary：{summary}",
        "",
        "## 建议",
        "- 暂停继续自动 revise",
        "- 直接人工检查当前草稿与 reviewer 问题，手动定稿或手动改一版后再继续流程",
    ]

    if major_issues:
        lines.extend(["", "## 主要问题"])
        lines.extend([f"- {item}" for item in major_issues])

    if minor_issues:
        lines.extend(["", "## 次要问题"])
        lines.extend([f"- {item}" for item in minor_issues])

    return "\n".join(lines).strip() + "\n"


def route_review_result(config: dict, task_text: str, draft_file: str, reviewer_result: dict) -> dict:
    locked_dir = config["paths"].get("locked_dir", "03_locked")
    working_dir = config["paths"].get("working_dir", "02_working")
    verdict = reviewer_result.get("verdict")
    created: dict[str, str] = {}

    if verdict == "lock":
        draft_content = read_text(draft_file)
        filename = Path(draft_file).name
        locked_file = build_locked_chapter_file(draft_file, locked_dir)
        candidate_file = f"{locked_dir}/candidates/{filename}"
        notes_file = f"{locked_dir}/canon/{Path(locked_file).stem}_notes.md"
        chapter_state_path = extract_markdown_field(task_text, "chapter_state")
        notes_proposal_file = f"{working_dir}/canon_updates/{Path(locked_file).stem}_notes_proposal.md"
        state_proposal_file = f"{working_dir}/canon_updates/{Path(locked_file).stem}_state_proposal.md"

        if (ROOT / locked_file).exists():
            print(f"警告：正在覆盖已有 locked 文件: {locked_file}")

        save_text(locked_file, draft_content)
        save_text(candidate_file, draft_content)
        save_text(notes_file, build_locked_notes_content(task_text, reviewer_result, draft_file, locked_file))
        save_text(
            notes_proposal_file,
            build_working_notes_proposal_content(task_text, reviewer_result, draft_file, locked_file, notes_file),
        )
        save_text(
            state_proposal_file,
            build_working_state_proposal_content(task_text, reviewer_result, locked_file, chapter_state_path),
        )
        created["locked_file"] = locked_file
        created["candidate_file"] = candidate_file
        created["notes_file"] = notes_file
        created["notes_proposal_file"] = notes_proposal_file
        created["state_proposal_file"] = state_proposal_file
        return created

    mode = "revise" if verdict == "revise" else "rewrite"
    generated_dir = f"{config['paths'].get('inputs_dir', '01_inputs')}/tasks/generated"
    max_revisions = int(config.get("generation", {}).get("max_auto_revisions", 5))
    task_id = extract_markdown_field(task_text, "task_id") or "generated-task"

    if mode == "revise" and extract_revision_count(task_id) >= max_revisions:
        manual_intervention_file = f"{working_dir}/reviews/{task_id}_manual_intervention.md"
        save_text(
            manual_intervention_file,
            build_manual_intervention_content(task_text, reviewer_result, draft_file, max_revisions),
        )
        created["manual_intervention_file"] = manual_intervention_file
        return created

    suffix = "revision_auto" if mode == "revise" else "rewrite_auto"
    task_file = f"{generated_dir}/{task_id}_{suffix}.md"
    task_content = build_generated_task_content(task_text, reviewer_result, draft_file, mode)
    save_text(task_file, task_content)
    created["task_file"] = task_file
    return created

def main() -> None:
    try:
        config = load_yaml("app/config.yaml")

        print("步骤 1/3：正在整理当前上下文...")
        current_context = compile_context(config)
        print(f"已生成上下文文件: {config['output']['context_file']}")

        print("步骤 2/3：正在生成草稿...")
        draft_result = write_draft(config, current_context)

        print("步骤 3/3：正在执行审稿与后续分流...")
        _, reviewer_json_path = review_scene_file(config, draft_result["draft_file"])
        reviewer_result = json.loads(read_text(reviewer_json_path))
        created = route_review_result(
            config,
            draft_result["task_text"],
            draft_result["draft_file"],
            reviewer_result,
        )

        print(f"已保存 reviewer 结果: {reviewer_json_path}")
        if reviewer_result.get("verdict") == "lock":
            print(f"已自动锁定到 {created['locked_file']}")
            print("如需人工修订，请直接编辑 locked 文件")
            print(f"已生成候选锁定文件: {created['candidate_file']}")
            print(f"已生成锁定 notes 草稿: {created['notes_file']}")
            print(f"已生成 working notes 更新提议: {created['notes_proposal_file']}")
            print(f"已生成 working state 更新提议: {created['state_proposal_file']}")
        elif "manual_intervention_file" in created:
            print("已达到最大自动修订次数（5次），请人工介入。")
            print(f"已生成人工介入提醒: {created['manual_intervention_file']}")
        else:
            print(f"已生成后续任务草稿: {created['task_file']}")

        print("本次自动闭环完成。")

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