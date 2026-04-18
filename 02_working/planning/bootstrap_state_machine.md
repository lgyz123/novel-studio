# 前置状态机

- planner/bootstrap agent：deterministic prewrite bootstrap
- task_id：2026-04-18-005_ch01_scene03_auto-R2
- chapter_id：ch01
- next_stage：第一章撰写

## 阶段推进
1. 世界观补全
状态：complete
产物：02_working/planning/worldview_patch.md
说明：已根据 prewrite review 生成 proposal。
2. 时间线补全
状态：complete
产物：02_working/planning/timeline_patch.md
说明：已根据 chapter_state 与 story_state 生成 proposal。
3. 角色创建
状态：complete
产物：02_working/planning/character_patch.md
说明：已有角色设定基础，可继续补功能卡。
4. 大纲定制
状态：complete
产物：02_working/outlines/ch01_outline.md
说明：章节 working outline 已生成。
5. 第一章撰写
状态：in_progress
产物：02_working/drafts/ch01_scene03_v3.md
说明：当前任务已进入 scene 落稿。

## 当前缺口提醒
- 世界观缺口：当前无显著缺口
- 时间线缺口：当前无显著缺口
- 这一状态机只推进 working proposal，不直接改写 locked canon。

## planning skill router

- phase：planning_bootstrap
- genre_tags：xianxia
- trope_tags：system
- demand_tags：planning、worldbuilding、outline-driven

## selected_skills
- worldbuilding｜mode=institutional｜score=0.92｜planning/bootstrap 阶段需要把抽象设定补成可执行的世界观补丁。
- scene-outline｜mode=chapter-outline｜score=0.88｜planning/bootstrap 阶段需要把章节目标压成可写的结构骨架。

## rejected_candidates
- timeline-history｜mode=chapter-sequence｜score=0.46｜时间线补全在 bootstrap 内单独走 timeline patch，本轮主路由先聚焦世界观和大纲。
- continuity-guard｜mode=scene-canon｜score=0.24｜此阶段以补 planning proposal 为主，还不是正文落稿校验阶段。

## risk_flags
- 无
