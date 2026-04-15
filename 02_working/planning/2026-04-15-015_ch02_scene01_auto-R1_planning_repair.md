# planning repair brief

- task_id：2026-04-15-015_ch02_scene01_auto-R1
- 说明：本文件由 skill audit 自动生成，用于指导修订前先重建 planning working 资产。

## repair order
1. 先修复下列 planning / routing 资产。
2. 确认 skill router 与 working proposal 已一致。
3. 再根据修复后的 planning 资产继续正文修订。

## repair targets
### planning_bootstrap
- focus：重建 worldbuilding / scene-outline 的 bootstrap 产物，并同步核对章节 outline。
- artifact：02_working/planning/worldview_patch.md
- router：02_working/planning/planning_bootstrap_skill_router.json
- source_issue：planning_bootstrap router 当前启用：worldbuilding、scene-outline。

### character_creation
- focus：重建角色功能卡、命名槽位与角色补全 proposal，再继续正文修订。
- artifact：02_working/planning/character_patch.md
- router：02_working/planning/character_creation_skill_router.json
- source_issue：character_creation router 当前启用：character-design、naming。

### timeline_bootstrap
- focus：重建章节时间承接、历史锚点与 timeline proposal，再继续正文修订。
- artifact：02_working/planning/timeline_patch.md
- router：02_working/planning/timeline_bootstrap_skill_router.json
- source_issue：timeline_bootstrap router 当前启用：timeline-history。

### scene_writing
- focus：先纠正 scene_writing 的 selected_skills，再进行正文修订。
- artifact：02_working/planning/scene_writing_skill_router.md
- router：02_working/planning/scene_writing_skill_router.json
- source_issue：scene_writing router 当前启用：continuity-guard、naming。
