import json
import re
from pathlib import Path
from typing import Any


def parse_markdown_sections(markdown_text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections[current_section] = []
            continue
        if current_section:
            sections[current_section].append(line)

    return sections


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _first_matches(text: str, keywords: list[str], limit: int = 3) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        if keyword in text and keyword not in hits:
            hits.append(keyword)
        if len(hits) >= limit:
            break
    return hits


def review_world_bible(world_bible_text: str, novel_manifest_text: str = "") -> dict[str, Any]:
    combined = "\n".join([world_bible_text, novel_manifest_text]).strip()

    dimensions = [
        {
            "id": "core_rules",
            "label": "核心法则",
            "keywords": ["修行逻辑", "命、愿、债", "天道", "核心", "法则", "规则"],
            "missing_message": "缺少可执行的世界底层规则，当前更像主题宣言。",
            "completion_hint": "补出力量来源、代价、边界条件，以及它们如何影响普通人生计。",
        },
        {
            "id": "ecology_and_social_response",
            "label": "生态位与社会应对",
            "keywords": ["王朝", "宗门", "司命机构", "豪强", "寺观", "制度", "灵税", "功牌", "债册"],
            "missing_message": "缺少世界异常现象与社会秩序之间的联动说明。",
            "completion_hint": "补出危险事物的生态位，以及民间、官府、宗门各自的应对方式。",
        },
        {
            "id": "space_and_stage",
            "label": "时空舞台",
            "keywords": ["运河", "城市", "山门", "矿场", "寺观", "卷", "舞台", "地理"],
            "missing_message": "缺少主要舞台的空间层次和地域差异。",
            "completion_hint": "补出核心地理带、资源流向、不同地区的生存方式与视觉标志。",
        },
        {
            "id": "history_and_change",
            "label": "历史与变迁",
            "keywords": ["王朝更迭", "战争", "革命", "飞升", "旧制", "变法", "历史"],
            "missing_message": "缺少可追踪的历史节点，世界像静态背景板。",
            "completion_hint": "补出至少 3-5 个关键历史事件，并说明它们如何塑造当下秩序。",
        },
        {
            "id": "core_conflicts",
            "label": "核心矛盾",
            "keywords": ["反对内卷", "制度", "吃人", "众生", "代价", "冲突", "矛盾"],
            "missing_message": "冲突主题明确，但缺少世界层面的压力链条。",
            "completion_hint": "补出底层、体制内、超越体制三层冲突如何互相牵动。",
        },
    ]

    checks: list[dict[str, Any]] = []
    missing_dimensions: list[str] = []
    inferred_completions: list[str] = []
    strengths: list[str] = []

    for dimension in dimensions:
        matched_keywords = _first_matches(combined, dimension["keywords"])
        status = "ok" if matched_keywords else "missing"
        if status == "ok":
            strengths.append(f"{dimension['label']}已有锚点：{', '.join(matched_keywords)}")
        else:
            missing_dimensions.append(dimension["label"])
            inferred_completions.append(dimension["completion_hint"])
        checks.append(
            {
                "id": dimension["id"],
                "label": dimension["label"],
                "status": status,
                "evidence": matched_keywords,
                "issue": "" if status == "ok" else dimension["missing_message"],
                "completion_hint": dimension["completion_hint"],
            }
        )

    summary = "世界观基础可用，但存在待补完区域。" if missing_dimensions else "世界观主框架较完整，可直接进入写作。"
    return {
        "summary": summary,
        "strengths": strengths[:4],
        "missing_dimensions": missing_dimensions,
        "checks": checks,
        "inferred_completions": inferred_completions[:4],
    }


def _load_story_state(root: Path) -> dict[str, Any]:
    story_state_path = root / "03_locked/state/story_state.json"
    if not story_state_path.exists():
        return {}
    try:
        data = json.loads(story_state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _recent_timeline_events(story_state: dict[str, Any]) -> list[str]:
    timeline = story_state.get("timeline", {}) if isinstance(story_state, dict) else {}
    events = timeline.get("recent_events", []) if isinstance(timeline, dict) else []
    if not isinstance(events, list):
        return []
    return [str(item).strip() for item in events if str(item).strip()]


def review_timeline(
    novel_manifest_text: str,
    chapter_state_text: str = "",
    story_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    story_state = story_state or {}
    combined = "\n".join([novel_manifest_text, chapter_state_text]).strip()
    recent_events = _recent_timeline_events(story_state)
    current_book_time = ""
    timeline_state = story_state.get("timeline", {}) if isinstance(story_state, dict) else {}
    if isinstance(timeline_state, dict):
        current_book_time = str(timeline_state.get("current_book_time") or "").strip()

    dimensions = [
        {
            "id": "macro_arc",
            "label": "长线时间轴",
            "ok": _contains_any(novel_manifest_text, ["第一卷", "第二卷", "第三卷", "第四卷", "第五卷", "第六卷"]),
            "issue": "已有分卷节奏，但还缺少更细的世界历史节点。",
            "completion_hint": "补出世界历史大事年表，至少标出旧制形成、重大灾变、体制升级三个节点。",
        },
        {
            "id": "historical_events",
            "label": "历史事件锚点",
            "ok": _contains_any(combined, ["战争", "更迭", "革命", "灾荒", "变法", "飞升"]),
            "issue": "时间线中缺少明确的过去事件名称或类型。",
            "completion_hint": "把王朝更迭、战争、灾荒、技术或修行制度转折写成可引用的事件名。",
        },
        {
            "id": "present_progress",
            "label": "当前剧情时点",
            "ok": bool(current_book_time) or _contains_any(chapter_state_text, ["今夜", "傍晚", "次日", "夜里", "白天"]),
            "issue": "缺少当前剧情所在时间点，场景承接容易漂移。",
            "completion_hint": "在任务或 state 中显式记录当前时段、与上一场的间隔、关键事件先后。",
        },
        {
            "id": "recent_canon_events",
            "label": "近期正典事件",
            "ok": bool(recent_events),
            "issue": "story_state 对近期事件记录过薄，写作时难以做连续承接。",
            "completion_hint": "锁定后稳定回填 recent_events，并在写前挑最近 3 个事件进入上下文。",
        },
    ]

    checks: list[dict[str, Any]] = []
    missing_dimensions: list[str] = []
    inferred_completions: list[str] = []
    strengths: list[str] = []

    for dimension in dimensions:
        status = "ok" if dimension["ok"] else "missing"
        if status == "ok":
            strengths.append(dimension["label"])
        else:
            missing_dimensions.append(dimension["label"])
            inferred_completions.append(dimension["completion_hint"])
        checks.append(
            {
                "id": dimension["id"],
                "label": dimension["label"],
                "status": status,
                "issue": "" if status == "ok" else dimension["issue"],
                "completion_hint": dimension["completion_hint"],
            }
        )

    summary = "时间线有基础骨架，但写前承接信息仍偏薄。" if missing_dimensions else "时间线层次较完整，可直接承接写作。"
    return {
        "summary": summary,
        "current_book_time": current_book_time or "unknown",
        "recent_events": recent_events[:5],
        "strengths": strengths[:4],
        "missing_dimensions": missing_dimensions,
        "checks": checks,
        "inferred_completions": inferred_completions[:4],
    }


def build_prewrite_review(root: Path, task_text: str, chapter_state_text: str = "") -> dict[str, Any]:
    novel_manifest_text = (root / "00_manifest/novel_manifest.md").read_text(encoding="utf-8")
    world_bible_text = (root / "00_manifest/world_bible.md").read_text(encoding="utf-8")
    story_state = _load_story_state(root)

    world_review = review_world_bible(world_bible_text, novel_manifest_text=novel_manifest_text)
    timeline_review = review_timeline(
        novel_manifest_text,
        chapter_state_text=chapter_state_text,
        story_state=story_state,
    )

    return {
        "task_id": _extract_markdown_field(task_text, "task_id") or "unknown-task",
        "world_review": world_review,
        "timeline_review": timeline_review,
    }


def _extract_markdown_field(task_text: str, field_name: str) -> str | None:
    pattern = rf"(?ms)^#\s*{re.escape(field_name)}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, task_text)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


def render_prewrite_review_markdown(review: dict[str, Any]) -> str:
    world_review = review.get("world_review", {}) if isinstance(review, dict) else {}
    timeline_review = review.get("timeline_review", {}) if isinstance(review, dict) else {}

    def _lines(items: list[str], prefix: str = "- ") -> list[str]:
        return [f"{prefix}{item}" for item in items if str(item).strip()]

    lines = [
        "第一步：铺陈世界观",
        "",
        "【世界观构建】 已启动",
        "确立核心法则…",
        "",
        "- 我正在审视现有 manifest，确认力量体系、社会规则和天道逻辑是否已经闭环。",
    ]
    lines.extend(_lines(world_review.get("strengths", [])))
    if world_review.get("missing_dimensions"):
        lines.append("- 当前仍待补足：%s" % "；".join(world_review["missing_dimensions"]))
    lines.extend(_lines(world_review.get("inferred_completions", [])))

    lines.extend(
        [
            "",
            "推演内在逻辑…",
            "",
            "- 写作前需要先确认异常事物的生态位、制度反应和普通人的生存代价，否则场景容易只剩气氛没有后果。",
            "",
            "勾勒时空轮廓…",
            "",
            "- 我会优先检查主要舞台、历史变迁和当前剧情时点能否支持这一场 scene 的承接。",
            "",
            "植入核心矛盾…",
            "",
            "- 世界设定不仅要说明有什么，更要说明谁会因此受益、谁会因此受损、冲突如何落到人身上。",
            "",
            "第二步：校准时间线",
            "",
            "【时间线校验】 已启动",
            "梳理长线骨架…",
            "",
            f"- 当前 book time：{timeline_review.get('current_book_time', 'unknown')}",
        ]
    )
    if timeline_review.get("recent_events"):
        lines.extend(_lines([f"近期事件：{event}" for event in timeline_review["recent_events"]]))
    if timeline_review.get("missing_dimensions"):
        lines.append("- 当前仍待补足：%s" % "；".join(timeline_review["missing_dimensions"]))
    lines.extend(_lines(timeline_review.get("inferred_completions", [])))

    return "\n".join(lines).strip() + "\n"


def save_prewrite_review(root: Path, review: dict[str, Any], rel_path: str = "02_working/context/prewrite_review.md") -> str:
    output_path = root / rel_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_prewrite_review_markdown(review), encoding="utf-8")
    return rel_path
