# 角色补全 proposal

- planner/bootstrap agent：deterministic prewrite bootstrap
- task_id：2026-04-19-019_ch01_scene20_auto-R2
- chapter_id：ch01
- 写入位置：02_working/planning/character_patch.md
- 说明：这一版用于串联“角色创建”阶段，让前置状态机有明确产物。

## 当前核心角色槽位
- 主视角角色：孟浮灯
- 支撑角色：承接日常劳动、交易、邻里或组织压力的低烈度人物。
- 压力源角色：不必立刻正面出场，但需要在制度、传闻、搜检或监视中留下痕迹。

## 建议补全内容
- 为 孟浮灯 补三类可直接写进 scene 的信息：求活动作、避险习惯、被触发时的默认选择。
- 为章内高频配角补“功能卡”而非长传记：他们提供什么阻力、信息或情绪偏移。
- 如果暂不引入关键对手本人，也要先定义其外部投影：谁替他行事、留下什么后果、如何改变空间气氛。

## 使用原则
- 角色补全要优先服务于动作选择，不要先堆身世。
- 一切角色卡都应能回答：他/她在这一章里怎样改变主角的求活方式。

## character_creation skill router

- phase：character_creation
- genre_tags：xianxia、romance
- trope_tags：system
- demand_tags：planning、character、naming

## selected_skills
- character-design｜mode=protagonist-card｜score=0.91｜character_creation 阶段需要先明确角色功能卡、行为锚点和关系张力。
- naming｜mode=person｜score=0.86｜character_creation 阶段需要把角色槽位转成可用名字候选与命名风格约束。

## rejected_candidates
- continuity-guard｜mode=scene-canon｜score=0.28｜当前仍处于角色补全过程，尚未进入正文连续性校验。

## risk_flags
- 无

## 使用中的 skill：character-design
来源文件：skills/character-design/SKILL.md

# Character Design

Use this skill to build role cards that are small, functional, and scene-usable.

## Use when

- The task asks for character setup, role cards, supporting roles, or relationship tension.
- Planning/bootstrap needs a sharper protagonist, supporting role, or pressure source.
- A scene depends on how a person behaves, speaks, blocks, tempts, or redirects action.

## Do not use when

- The task is only naming.
- The task is only worldbuilding or timeline work.
- The task already has a complete locked role card and only needs continuity checking.

## Required inputs

Read only what is necessary:

- `01_inputs/tasks/current_task.md`
- relevant excerpts from `00_manifest/character_bible.md`
- chapter outline or planning notes if the char

[已截断]

参考：skills/character-design/references/cards.md

# Character Card Patterns

## Protagonist card

- core drive
- avoidance pattern
- default action under pressure
- what this person notices first

## Supporting-role card

- external function
- pressure style
- behavior markers
- speech tendency

## Rule

If a field cannot affect

[已截断]

参考：skills/character-design/references/tension.md

# Relationship Tension

Good tension design answers:

- what the other person makes harder
- what they make easier
- what they force the protagonist to hide or reveal
- whether the pressure is open, ambient, or indirect

Prefer asymmetry and friction over symmetrical labels like

[已截断]

## 使用中的 skill：naming
来源文件：skills/naming/SKILL.md

# Naming

Use this skill to generate names that fit the project's genre, social layer, tone, and existing canon.

## Use when

- The task explicitly asks for naming, titles, labels, or candidate lists.
- Character creation needs a person name.
- Worldbuilding needs place names, sect names, artifact names, or technique names.
- Outline work needs placeholder names upgraded into usable canon candidates.

## Do not use when

- The task already has fixed canon names.
- The task is about prose refinement with no naming need.

## Required inputs

Read only what you need:

- `01_inputs/tasks/current_task.md`
- relevant character or world manifest excerpts
- existing canon names when collision risk matters

## Workflow

[已截断]

参考：skills/naming/references/person.md

# Person Naming

## Inputs that matter

- gender or presentation
- social class
- regional flavor
- era feel
- role weight: protagonist / supporting / one-scene role

## Good candidate properties

- readable
- fits the genre
- memorable without being noisy
- g

[已截断]

参考：skills/naming/references/world.md

# World Naming

Use these questions:

- Is this name for a place, organization, artifact, or technique?
- Should it sound official, vernacular, sacred, feared, or commercial?
- Does it come from local speech, institutional naming, or inherited older language?

[已截断]
