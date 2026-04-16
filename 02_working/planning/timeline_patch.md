# 时间线补全 proposal

- planner/bootstrap agent：deterministic prewrite bootstrap
- task_id：2026-04-16-029_ch02_scene03_auto
- chapter_id：ch02
- 写入位置：02_working/planning/timeline_patch.md
- 说明：以下时间线只作为写前承接候选，不直接覆盖 story_state。

## 当前时间锚点
- current_book_time：夜间
- recent_event：EVENT-001
- recent_event：EVENT-002
- recent_event：EVENT-003
- recent_event：EVENT-004
- recent_event：EVENT-005

## 章节承接锚点
- 直接前文：03_locked/chapters/ch01_scene11.md

## 待补维度
- 当前时间线骨架可用。

## 建议时间线补丁

### 世界历史锚点
- 旧制成形：确立今天仍在运作的税役、差序和风险转嫁办法。
- 大灾或大战：解释为什么底层岗位被迫吸纳更多危险工作。
- 体制加码：说明当前制度为何更重登记、搜检、盘剥或隐性抽税。

### 本卷承接锚点
- 明确第一卷的起点时段、前三个关键局面变化、以及每次变化与上一场之间隔了多久。
- 如果 chapter_state 只写“夜里 / 次日 / 白天”，建议补一行相对顺序说明，避免 scene 承接漂移。

### 本章承接规则
- 每一场至少显式标明一个时间信号：夜里、次日清早、午后、傍晚、隔日等。
- 每次风险升级都要同步写明它发生在什么时段、和上一场相隔多久、为什么来得及或来不及处理。

## timeline skill router

- phase：timeline_bootstrap
- genre_tags：xianxia
- trope_tags：system
- demand_tags：planning、timeline、history

## selected_skills
- timeline-history｜mode=chapter-sequence｜score=0.93｜timeline_bootstrap 阶段需要把历史锚点与章节承接显式化。

## rejected_candidates
- worldbuilding｜mode=institutional｜score=0.31｜本轮重点是时间承接和历史锚点，不是制度补丁主导。
- continuity-guard｜mode=timeline-check｜score=0.29｜当前仍是写前时间策划，不是正文连续性修复。

## risk_flags
- 无

## 使用中的 skill：timeline-history
来源文件：skills/timeline-history/SKILL.md

# Timeline History

Use this skill to make chronology explicit enough for planning and scene writing to stay stable.

## Use when

- The project needs historical anchors or chapter-sequence planning.
- A scene must clearly bridge from the previous time point.
- The task mentions current time, next day, prior event, or historical context.
- The writer needs help preventing time blur.

## Do not use when

- The task is pure naming.
- The task is only prose style enhancement.
- The task is only continuity checking with no timeline gap.

## Required inputs

Read only what is necessary:

- `01_inputs/tasks/current_task.md`
- `03_locked/canon/chXX_state.md` if present
- `03_locked/state/story_state.json`
- planning patches when they alr

[已截断]

参考：skills/timeline-history/references/anchors.md

# Time Anchors

## World-history anchors

Use only when they still leave present traces:

- old regime formation
- war or disaster
- reform, crackdown, or institutional escalation

## Chapter-sequence anchors

Keep these explicit:

- current time of day
- gap from previous scene
- what changed durin

[已截断]

参考：skills/timeline-history/references/drift.md

# Timeline Drift

## Same-night blur

Pattern:

- prior scene ends at night
- new scene is next morning but still reads like the same night

Fix:

- mark the time early
- give one sensory sign of the changed hour

## History overload

Pattern:

- timeline note turns into an isolated history lecture

[已截断]
