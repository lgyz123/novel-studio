import re


def is_mostly_english(text: str) -> bool:
    english_chars = len(re.findall(r"[A-Za-z]", text))
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    return english_chars > chinese_chars * 2 and english_chars > 20


def is_task_restatement(text: str) -> bool:
    lower_text = text.lower().strip()
    markers = [
        "the task:",
        "must not introduce",
        "must not",
        "constraints:",
        "current task",
        "preferred_length",
        "output_target",
    ]
    return any(marker in lower_text for marker in markers)


def is_thinking_trace(text: str) -> bool:
    lower_text = text.lower().strip()
    markers = [
        "we need to check",
        "maybe",
        "but maybe",
        "so maybe",
        "let's",
        "let us",
        "i think",
        "we should check",
        "需要检查",
        "也许",
        "可能是",
        "先看看",
    ]
    return any(marker in lower_text for marker in markers)


def extract_allowed_light_characters(task_text: str | None) -> list[str]:
    if not task_text:
        return []

    allowed: list[str] = []
    patterns = [
        r"([一-龥A-Za-z0-9_]+)可以不出场；如出场，只能极轻",
        r"([一-龥A-Za-z0-9_]+)可以.*极轻",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, task_text):
            allowed.append(match.group(1))
    return list(set(allowed))


def is_false_character_issue(text: str, task_text: str | None) -> bool:
    if not task_text:
        return False

    allowed_light = extract_allowed_light_characters(task_text)
    if any(name in text for name in allowed_light):
        if "新人物" in text or "违反" in text:
            return True

    if "更夫" in text and "新人物" in text:
        return True

    return False


def is_task_line_duplicate(text: str, task_text: str | None) -> bool:
    if not task_text:
        return False

    short_lines = [
        line.strip("- ").strip()
        for line in task_text.splitlines()
        if line.strip()
    ]
    return any(len(line) >= 4 and text == line for line in short_lines)


def filter_shared_issues(items: list[str], task_text: str | None = None, limit: int | None = None) -> list[str]:
    cleaned: list[str] = []

    for item in items:
        text = str(item).strip()
        if not text:
            continue
        if is_task_restatement(text):
            continue
        if is_thinking_trace(text):
            continue
        if is_mostly_english(text):
            continue
        if is_task_line_duplicate(text, task_text):
            continue
        if is_false_character_issue(text, task_text):
            continue
        cleaned.append(text)

    if limit is not None:
        return cleaned[:limit]
    return cleaned