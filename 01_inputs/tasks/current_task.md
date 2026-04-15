# task_id
2026-04-15-009_ch02_scene01_auto-R2

# goal
基于上一版草稿整体重写当前 scene：写出第 2 章第 1 个短场景，承接前文并为本章建立新的局面。 本章重点：进入体制内部，看见精致化压榨与晋升神话 当前章节目标：第二章先确立新的日常压力源，再让主角被迫形成更明确的应对方式。本次重点解决：先核对 `02_working/planning/worldview_patch.md`、`02_working/outlines/chapter_outline` 与 `planning_bootstrap_skill_router.json`，修正 worldbuilding / scene-outline 的选择或产物，再继续改正文。；先核对 `02_working/planning/character_patch.md` 与 `character_creation_skill_router.json`，修正角色功能卡或命名槽位，再继续改正文。；围绕该问题重写相关场段，确保核心目标与约束重新成立。问题：当前草稿未充分完成 task 的核心推进目标。；在对应位置局部改写，直接修复该问题，不扩散到整场。问题：Reviewer 原始输出主要是无效英文分析，已降权处理。；在对应位置局部改写，直接修复该问题，不扩散到整场。问题：[skill audit][planning_bootstrap] planning_bootstrap router 当前启用：worldbuilding、scene-outline。

# based_on
02_working/drafts/ch02_scene01_v2.md

# scene_purpose
本场结束时必须形成新的章内起点，不能只是重复上章余波。

# required_information_gain
- 保持与项目故事梗概一致：孟浮灯在运河与码头底层求活时，被一具来历异常的尸体和它牵出的名字卷入更大的秩序黑幕。
- 补入至少一个只属于本章的新事实、新限制或新压力来源。
- 让主角对当前局面产生新的理解、误判或行动边界。
- 新章开场必须出现新的现实问题，不只是延续上一章余波。
- 主角要做出一次带后果的微决策。

# required_plot_progress
本场必须把上一章后的局面真正往前推一步，为本章建立新的现实问题。

# required_decision_shift
主角必须做出一个会影响本章后续处理方式的新动作或新决定。

# required_state_change
- 至少一个状态变量改变：已知信息 / 风险等级 / 行动计划 / 关系态势 / 物件位置。

# chapter_state
03_locked/canon/ch02_state.md

# repair_mode
full_redraft

# repair_focus
prose_repair

# repair_plan
02_working/reviews/2026-04-15-009_ch02_scene01_auto-R1_repair_plan.json

# planning_repair_brief
02_working/planning/2026-04-15-009_ch02_scene01_auto-R2_planning_repair.md

# review_trace
- provider: ollama
- mode: deterministic_primary_with_reference
- low_confidence: yes
- deterministic_fallback: yes
- json_refinement_attempted: no
- repeated_fragments: 18

# constraints
- 保持连续小说 prose，不写说明、提纲或分镜。
- 不要擅自跳出当前章的现实承接。
- 主角核心仍是 孟浮灯。
- 类型基调保持为：底层现实主义修仙
- 不要现代词汇、现代设施、现代口语。
- 不要后宫、脸谱反派、流水线升级。
- 避免拍点：不要一上来就把更高层真相全部掀开。
- 避免拍点：不要跳成大场面冲突或爽文式反击。
- structural_repair 允许动作：
- 允许补入一个关键动作、新事实、动作后果或结尾状态变化。
- 必须把 scene contract 缺失项补写落地，不能只做语言微修。
- 修订模式：full_redraft
- 修订焦点：prose_repair
- prose_repair 约束：优先修衔接、语言密度、节奏与表达稳定性，尽量不改大结构。
- skill audit 纠偏优先级：
- 先核对 `02_working/planning/worldview_patch.md`、`02_working/outlines/chapter_outline` 与 `planning_bootstrap_skill_router.json`，修正 worldbuilding / scene-outline 的选择或产物，再继续改正文。
- 先核对 `02_working/planning/character_patch.md` 与 `character_creation_skill_router.json`，修正角色功能卡或命名槽位，再继续改正文。
- 先核对 `02_working/planning/timeline_patch.md` 与 `timeline_bootstrap_skill_router.json`，修正章节时间承接和历史锚点，再继续改正文。
- 正文修订前先核对 `scene_writing_skill_router.json` 的 selected_skills，确保 `continuity-guard` 等必要 skill 已正确挂载。
- repair_plan 执行动作：
- 围绕该问题重写相关场段，确保核心目标与约束重新成立。问题：当前草稿未充分完成 task 的核心推进目标。
- 在对应位置局部改写，直接修复该问题，不扩散到整场。问题：Reviewer 原始输出主要是无效英文分析，已降权处理。
- 在对应位置局部改写，直接修复该问题，不扩散到整场。问题：[skill audit][planning_bootstrap] planning_bootstrap router 当前启用：worldbuilding、scene-outline。
- 在对应位置局部改写，直接修复该问题，不扩散到整场。问题：[skill audit][character_creation] character_creation router 当前启用：character-design、naming。
- 在对应位置局部改写，直接修复该问题，不扩散到整场。问题：[skill audit][timeline_bootstrap] timeline_bootstrap router 当前启用：timeline-history。

# preferred_length
1500-2600字

# output_target
02_working/drafts/ch02_scene01_v3.md
