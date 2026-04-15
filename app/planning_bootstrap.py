import json
import re
from pathlib import Path
from typing import Any

from prewrite_checks import build_prewrite_review
from skill_router import render_skill_router_markdown, route_writer_skills, save_skill_router_outputs
from writer_skills import build_selected_skill_sections, build_skill_section


def extract_markdown_field(task_text: str, field_name: str) -> str | None:
    pattern = rf"(?ms)^#\s*{re.escape(field_name)}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, task_text)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


def infer_chapter_id(task_text: str, chapter_state_path: str = "", output_target: str = "") -> str:
    candidates = [task_text, chapter_state_path, output_target]
    for candidate in candidates:
        match = re.search(r"(?<![A-Za-z0-9])(ch\d{2,})(?![A-Za-z0-9])", str(candidate))
        if match:
            return match.group(1)
    return "ch01"


def load_story_state(root: Path) -> dict[str, Any]:
    path = root / "03_locked/state/story_state.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _recent_events(story_state: dict[str, Any]) -> list[str]:
    timeline = story_state.get("timeline", {}) if isinstance(story_state, dict) else {}
    events = timeline.get("recent_events", []) if isinstance(timeline, dict) else []
    if not isinstance(events, list):
        return []
    return [str(item).strip() for item in events if str(item).strip()]


def _extract_chapter_state_scene_lines(chapter_state_text: str, limit: int = 6) -> list[str]:
    lines: list[str] = []
    for raw_line in chapter_state_text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("- ") and "scene" in stripped.lower():
            lines.append(stripped[2:].strip())
        if len(lines) >= limit:
            break
    return lines


def build_worldview_patch_markdown(
    root: Path,
    task_id: str,
    chapter_id: str,
    world_review: dict[str, Any],
    novel_manifest_text: str,
    world_bible_text: str,
) -> str:
    missing = [str(item).strip() for item in world_review.get("missing_dimensions", []) if str(item).strip()]
    strengths = [str(item).strip() for item in world_review.get("strengths", []) if str(item).strip()]
    lines = [
        "# 世界观补全 proposal",
        "",
        f"- planner/bootstrap agent：deterministic prewrite bootstrap",
        f"- task_id：{task_id}",
        f"- chapter_id：{chapter_id}",
        "- 写入位置：02_working/planning/worldview_patch.md",
        "- 说明：以下内容是写前补全候选，不直接进入 canon。",
        "",
        "## 当前锚点",
    ]

    if strengths:
        lines.extend([f"- {item}" for item in strengths[:4]])
    else:
        lines.append("- 现有 manifest 只给出方向性约束，缺少可写细节。")

    lines.extend(["", "## 待补维度"])
    if missing:
        lines.extend([f"- {item}" for item in missing])
    else:
        lines.append("- 当前没有显著缺口，可直接沿现有世界观写作。")

    section_templates = {
        "核心法则": [
            "- 把“命 / 愿 / 债”从主题口号落成三类可执行规则：谁能调动它、代价怎样结算、普通人怎么被波及。",
            "- 明确凡俗与修行者的边界条件：平民可感知什么，不能承受什么，越界后会付出什么现实成本。",
            "- 给出一条写作可直接调用的底层句式：任何超常便利都必须伴随可追踪的代价或债务。",
        ],
        "生态位与社会应对": [
            "- 补出异常事物进入日常秩序后的处理链：民间回避办法、官面登记办法、宗门或寺观的收容办法。",
            "- 明确制度怎样把风险转嫁给底层劳动者，例如收尸、搬运、守夜、税役、担保之类的岗位。",
            "- 规定不同阶层对同一异常现象的称呼差异，方便正文里自然体现身份落差。",
        ],
        "时空舞台": [
            "- 把主要舞台拆成三层：求活层、管制层、超常层，并分别给出最常见的空间场景。",
            "- 明确资源流向：运河 / 货栈 / 乱葬岗 / 寺观或衙门之间，哪些人从中受益，哪些人只能擦边活着。",
            "- 为每个核心地点补一个视觉标志和一个气味或声音标志，方便后续场景稳定复用。",
        ],
        "历史与变迁": [
            "- 增补 3-5 个世界历史节点，并说明它们怎样塑造当下秩序。",
            "- 推荐锚点：旧制成形、一次大灾或大战、一次体制加码、一次失败的反抗或改革。",
            "- 每个历史节点都要落到今天还看得见的痕迹，例如税法、地名、职业分工、禁忌或废弃设施。",
        ],
        "核心矛盾": [
            "- 把核心冲突拆成三层：底层求活冲突、体制内维稳冲突、超越体制的终极冲突。",
            "- 规定每一层冲突如何向下一层传导，让人物的日常动作能自然承接世界主题。",
            "- 给正文留出可执行判断：任何世界设定都应能回答“谁因此更难活、谁因此更容易抽身”。",
        ],
    }

    lines.extend(["", "## 建议补丁"])
    if not missing:
        lines.append("- 本轮无需新增世界观补丁，建议保持 manifest 稳定。")
    else:
        for label in missing:
            lines.extend(["", f"### {label}"])
            lines.extend(section_templates.get(label, ["- 为该维度补出更可执行的写作细节。"]))

    manifest_anchor = "命、愿、债" if "命、愿、债" in world_bible_text else "现有总纲"
    lines.extend(
        [
            "",
            "## 与现有设定的衔接原则",
            f"- 新补丁必须回扣 `{manifest_anchor}` 这类现有锚点，不要另起一套力量体系。",
            "- 新补丁优先服务于场景可写性：能带来职业差异、风险后果、行动限制，而不是只增加名词。",
            "- 在未人工确认前，这些内容只作为 02_working proposal 进入 writer context。",
        ]
    )
    lines.extend(
        [
            "",
            build_skill_section(
                root,
                "worldbuilding",
                heading="## 使用中的 skill：worldbuilding",
                body_max_chars=750,
                references=["patch-patterns.md", "writer-hooks.md"],
                reference_max_chars=320,
            ).strip(),
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_timeline_patch_markdown(
    root: Path,
    task_id: str,
    chapter_id: str,
    timeline_review: dict[str, Any],
    chapter_state_text: str,
    story_state: dict[str, Any],
    router_result: dict[str, Any],
) -> str:
    missing = [str(item).strip() for item in timeline_review.get("missing_dimensions", []) if str(item).strip()]
    recent_events = _recent_events(story_state)
    current_book_time = str(timeline_review.get("current_book_time") or "unknown").strip() or "unknown"
    chapter_scene_lines = _extract_chapter_state_scene_lines(chapter_state_text)
    lines = [
        "# 时间线补全 proposal",
        "",
        f"- planner/bootstrap agent：deterministic prewrite bootstrap",
        f"- task_id：{task_id}",
        f"- chapter_id：{chapter_id}",
        "- 写入位置：02_working/planning/timeline_patch.md",
        "- 说明：以下时间线只作为写前承接候选，不直接覆盖 story_state。",
        "",
        "## 当前时间锚点",
        f"- current_book_time：{current_book_time}",
    ]

    if recent_events:
        lines.extend([f"- recent_event：{event}" for event in recent_events[:5]])
    else:
        lines.append("- recent_event：当前 story_state 记录不足，建议继续在 lock 后回填。")

    lines.extend(["", "## 章节承接锚点"])
    if chapter_scene_lines:
        lines.extend([f"- {item}" for item in chapter_scene_lines[:5]])
    else:
        lines.append("- 当前 chapter_state 里缺少明确的 scene 时序描述。")

    lines.extend(["", "## 待补维度"])
    if missing:
        lines.extend([f"- {item}" for item in missing])
    else:
        lines.append("- 当前时间线骨架可用。")

    lines.extend(
        [
            "",
            "## 建议时间线补丁",
            "",
            "### 世界历史锚点",
            "- 旧制成形：确立今天仍在运作的税役、差序和风险转嫁办法。",
            "- 大灾或大战：解释为什么底层岗位被迫吸纳更多危险工作。",
            "- 体制加码：说明当前制度为何更重登记、搜检、盘剥或隐性抽税。",
            "",
            "### 本卷承接锚点",
            "- 明确第一卷的起点时段、前三个关键局面变化、以及每次变化与上一场之间隔了多久。",
            "- 如果 chapter_state 只写“夜里 / 次日 / 白天”，建议补一行相对顺序说明，避免 scene 承接漂移。",
            "",
            "### 本章承接规则",
            "- 每一场至少显式标明一个时间信号：夜里、次日清早、午后、傍晚、隔日等。",
            "- 每次风险升级都要同步写明它发生在什么时段、和上一场相隔多久、为什么来得及或来不及处理。",
            "",
            render_skill_router_markdown(router_result, heading="## timeline skill router").strip(),
            "",
            build_selected_skill_sections(root, router_result.get("selected_skills", []), heading_prefix="## 使用中的 skill").strip(),
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_character_patch_markdown(root: Path, task_id: str, chapter_id: str, character_bible_text: str, router_result: dict[str, Any]) -> str:
    protagonist = "孟浮灯" if "孟浮灯" in character_bible_text else "当前主角"
    lines = [
        "# 角色补全 proposal",
        "",
        f"- planner/bootstrap agent：deterministic prewrite bootstrap",
        f"- task_id：{task_id}",
        f"- chapter_id：{chapter_id}",
        "- 写入位置：02_working/planning/character_patch.md",
        "- 说明：这一版用于串联“角色创建”阶段，让前置状态机有明确产物。",
        "",
        "## 当前核心角色槽位",
        f"- 主视角角色：{protagonist}",
        "- 支撑角色：承接日常劳动、交易、邻里或组织压力的低烈度人物。",
        "- 压力源角色：不必立刻正面出场，但需要在制度、传闻、搜检或监视中留下痕迹。",
        "",
        "## 建议补全内容",
        f"- 为 {protagonist} 补三类可直接写进 scene 的信息：求活动作、避险习惯、被触发时的默认选择。",
        "- 为章内高频配角补“功能卡”而非长传记：他们提供什么阻力、信息或情绪偏移。",
        "- 如果暂不引入关键对手本人，也要先定义其外部投影：谁替他行事、留下什么后果、如何改变空间气氛。",
        "",
        "## 使用原则",
        "- 角色补全要优先服务于动作选择，不要先堆身世。",
        "- 一切角色卡都应能回答：他/她在这一章里怎样改变主角的求活方式。",
        "",
        render_skill_router_markdown(router_result, heading="## character_creation skill router").strip(),
        "",
        build_selected_skill_sections(root, router_result.get("selected_skills", []), heading_prefix="## 使用中的 skill").strip(),
    ]
    return "\n".join(lines).strip() + "\n"


def build_chapter_outline_markdown(
    root: Path,
    task_id: str,
    chapter_id: str,
    task_text: str,
    chapter_state_text: str,
    story_state: dict[str, Any],
) -> str:
    goal = extract_markdown_field(task_text, "goal") or "围绕当前章节目标推进。"
    scene_lines = _extract_chapter_state_scene_lines(chapter_state_text, limit=8)
    recent_events = _recent_events(story_state)
    lines = [
        f"# {chapter_id}_outline 工作稿",
        "",
        f"- planner/bootstrap agent：deterministic prewrite bootstrap",
        f"- task_id：{task_id}",
        f"- chapter_id：{chapter_id}",
        "- 写入位置：02_working/outlines/%s_outline.md" % chapter_id,
        "- 说明：这是 working outline，不直接替代 00_manifest 或 locked canon。",
        "",
        "## 本章当前目标",
        f"- {goal}",
        "",
        "## 已有章节锚点",
    ]
    if scene_lines:
        lines.extend([f"- {item}" for item in scene_lines])
    else:
        lines.append("- 当前还缺少足够的章节锚点，建议用 locked scenes 或 chapter_state 补齐。")

    lines.extend(["", "## 建议章节骨架"])
    lines.extend(
        [
            "- 开场：先稳住主角当前求活状态与所处空间压力。",
            "- 扰动：让一个低烈度异常或旧线索重新压到日常动作上。",
            "- 试探：把线索从内部记挂推进到外部轻试探，但不要一次性升级成公开调查。",
            "- 后果：让试探带来可验证的新阻力、风险、信息或关系变化。",
            "- 章末偏移：主角形成新的处理方式，为下一章或下一场提供更明确的行为倾向。",
        ]
    )

    if recent_events:
        lines.extend(["", "## 近期正典事件提醒"])
        lines.extend([f"- {item}" for item in recent_events[:3]])

    lines.extend(
        [
            "",
            "## 与前置状态机的连接",
            "- 角色创建阶段：把主视角、支撑角色、压力源角色的功能卡补齐。",
            "- 大纲定制阶段：把上面的章节骨架改成当前项目真实的章内锚点与顺序。",
            "- 第一章撰写阶段：基于本 outline 和 scene contract 继续落到具体 scene 任务。",
            "",
            build_skill_section(
                root,
                "scene-outline",
                heading="## 使用中的 skill：scene-outline",
                body_max_chars=750,
                references=["contract-patterns.md", "chapter-shapes.md"],
                reference_max_chars=320,
            ).strip(),
        ]
    )
    return "\n".join(lines).strip() + "\n"


def build_bootstrap_state_machine_markdown(
    task_id: str,
    chapter_id: str,
    output_target: str,
    world_review: dict[str, Any],
    timeline_review: dict[str, Any],
    character_bible_text: str,
    router_result: dict[str, Any],
) -> str:
    has_character_seed = "### 孟浮灯" in character_bible_text or "孟浮灯" in character_bible_text
    is_chapter_writing = chapter_id == "ch01" and "02_working/drafts/" in output_target
    stages = [
        {
            "name": "世界观补全",
            "status": "complete",
            "artifact": "02_working/planning/worldview_patch.md",
            "notes": "已根据 prewrite review 生成 proposal。",
        },
        {
            "name": "时间线补全",
            "status": "complete",
            "artifact": "02_working/planning/timeline_patch.md",
            "notes": "已根据 chapter_state 与 story_state 生成 proposal。",
        },
        {
            "name": "角色创建",
            "status": "complete" if has_character_seed else "in_progress",
            "artifact": "02_working/planning/character_patch.md",
            "notes": "已有角色设定基础，可继续补功能卡。" if has_character_seed else "角色卡仍偏薄，建议先补功能卡再写章。",
        },
        {
            "name": "大纲定制",
            "status": "complete",
            "artifact": f"02_working/outlines/{chapter_id}_outline.md",
            "notes": "章节 working outline 已生成。",
        },
        {
            "name": "第一章撰写",
            "status": "in_progress" if is_chapter_writing else "pending",
            "artifact": output_target or "02_working/drafts/ch01_scene01.md",
            "notes": "当前任务已进入 scene 落稿。" if is_chapter_writing else "等待前置阶段确认后进入正文写作。",
        },
    ]

    next_stage = next((stage["name"] for stage in stages if stage["status"] in {"in_progress", "pending"}), "已进入持续写作")
    lines = [
        "# 前置状态机",
        "",
        f"- planner/bootstrap agent：deterministic prewrite bootstrap",
        f"- task_id：{task_id}",
        f"- chapter_id：{chapter_id}",
        f"- next_stage：{next_stage}",
        "",
        "## 阶段推进",
    ]
    for index, stage in enumerate(stages, start=1):
        lines.extend(
            [
                f"{index}. {stage['name']}",
                f"状态：{stage['status']}",
                f"产物：{stage['artifact']}",
                f"说明：{stage['notes']}",
            ]
        )
    lines.extend(
        [
            "",
            "## 当前缺口提醒",
            "- 世界观缺口：%s" % ("；".join(world_review.get("missing_dimensions", [])) or "当前无显著缺口"),
            "- 时间线缺口：%s" % ("；".join(timeline_review.get("missing_dimensions", [])) or "当前无显著缺口"),
            "- 这一状态机只推进 working proposal，不直接改写 locked canon。",
            "",
            render_skill_router_markdown(router_result, heading="## planning skill router").strip(),
        ]
    )
    return "\n".join(lines).strip() + "\n"


def save_text(root: Path, rel_path: str, content: str) -> str:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return rel_path


def run_planning_bootstrap(root: Path, task_text: str, chapter_state_text: str = "") -> dict[str, str]:
    task_id = extract_markdown_field(task_text, "task_id") or "unknown-task"
    output_target = extract_markdown_field(task_text, "output_target") or "02_working/drafts/ch01_scene01.md"
    chapter_state_path = extract_markdown_field(task_text, "chapter_state") or ""
    chapter_id = infer_chapter_id(task_text, chapter_state_path=chapter_state_path, output_target=output_target)
    novel_manifest_text = (root / "00_manifest/novel_manifest.md").read_text(encoding="utf-8")
    world_bible_text = (root / "00_manifest/world_bible.md").read_text(encoding="utf-8")
    character_bible_text = (root / "00_manifest/character_bible.md").read_text(encoding="utf-8")
    story_state = load_story_state(root)
    prewrite_review = build_prewrite_review(root, task_text, chapter_state_text=chapter_state_text)
    world_review = prewrite_review.get("world_review", {})
    timeline_review = prewrite_review.get("timeline_review", {})
    planning_router_result = route_writer_skills(
        phase="planning_bootstrap",
        task_text=task_text,
        project_manifest_text="\n".join([novel_manifest_text, world_bible_text]),
        state_signals=story_state,
    )
    character_router_result = route_writer_skills(
        phase="character_creation",
        task_text=task_text,
        project_manifest_text="\n".join([novel_manifest_text, world_bible_text, character_bible_text]),
        state_signals=story_state,
    )
    timeline_router_result = route_writer_skills(
        phase="timeline_bootstrap",
        task_text=task_text,
        project_manifest_text="\n".join([novel_manifest_text, world_bible_text]),
        state_signals=story_state,
    )

    worldview_patch_path = "02_working/planning/worldview_patch.md"
    timeline_patch_path = "02_working/planning/timeline_patch.md"
    character_patch_path = "02_working/planning/character_patch.md"
    outline_path = f"02_working/outlines/{chapter_id}_outline.md"
    state_machine_path = "02_working/planning/bootstrap_state_machine.md"
    planning_router_files = save_skill_router_outputs(
        root,
        "02_working/planning/planning_bootstrap_skill_router",
        planning_router_result,
        heading="# planning skill router",
    )
    character_router_files = save_skill_router_outputs(
        root,
        "02_working/planning/character_creation_skill_router",
        character_router_result,
        heading="# character_creation skill router",
    )
    timeline_router_files = save_skill_router_outputs(
        root,
        "02_working/planning/timeline_bootstrap_skill_router",
        timeline_router_result,
        heading="# timeline skill router",
    )

    save_text(
        root,
        worldview_patch_path,
        build_worldview_patch_markdown(root, task_id, chapter_id, world_review, novel_manifest_text, world_bible_text),
    )
    save_text(
        root,
        timeline_patch_path,
        build_timeline_patch_markdown(root, task_id, chapter_id, timeline_review, chapter_state_text, story_state, timeline_router_result),
    )
    save_text(
        root,
        character_patch_path,
        build_character_patch_markdown(root, task_id, chapter_id, character_bible_text, character_router_result),
    )
    save_text(
        root,
        outline_path,
        build_chapter_outline_markdown(root, task_id, chapter_id, task_text, chapter_state_text, story_state),
    )
    save_text(
        root,
        state_machine_path,
        build_bootstrap_state_machine_markdown(
            task_id,
            chapter_id,
            output_target,
            world_review,
            timeline_review,
            character_bible_text,
            planning_router_result,
        ),
    )

    return {
        "worldview_patch_file": worldview_patch_path,
        "timeline_patch_file": timeline_patch_path,
        "character_patch_file": character_patch_path,
        "outline_file": outline_path,
        "state_machine_file": state_machine_path,
        "planning_skill_router": planning_router_result,
        "character_creation_skill_router": character_router_result,
        "timeline_bootstrap_skill_router": timeline_router_result,
        "planning_skill_router_json_file": planning_router_files["json_file"],
        "planning_skill_router_md_file": planning_router_files["md_file"],
        "character_creation_skill_router_json_file": character_router_files["json_file"],
        "character_creation_skill_router_md_file": character_router_files["md_file"],
        "timeline_bootstrap_skill_router_json_file": timeline_router_files["json_file"],
        "timeline_bootstrap_skill_router_md_file": timeline_router_files["md_file"],
    }
