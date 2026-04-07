# 2026-04-03-006-RW6 人工介入说明

## 当前状态
- 当前任务：`2026-04-03-006-RW6`
- 当前草稿：`02_working/drafts/ch01_scene03_v3_rewrite_v4_rewrite6.md`
- 当前结论：`revise`
- 当前摘要：已达到修订阈值 5 轮，建议人工介入。
- 自动修订上限：5
- 已记录修订轮次：11
- 重复问题类型：scene_purpose

## 为什么自动化停止
- 已达到修订阈值 5 轮，建议人工介入。 supervisor 接管轮次已用尽。
- 已达到修订阈值 5 轮，建议人工介入。

## 当前未解决的关键问题
- `ISSUE-001` `scene_purpose` `high` `2026-04-03-006-RW6`：已达到修订阈值 5 轮，建议人工介入。
- `ISSUE-002` `scene_purpose` `critical` `2026-04-03-006-RW6`：当前草稿未充分完成 task 的核心推进目标。
- `ISSUE-003` `scene_purpose` `medium` `2026-04-03-006-RW6`：Reviewer 原始输出主要是无效英文分析，已降权处理。

## 可能根因
- 已达到修订阈值 5 轮，建议人工介入。 supervisor 接管轮次已用尽。
- 已达到修订阈值 5 轮，建议人工介入。
- 当前 repair_mode 为 `full_redraft`，说明问题规模已超出纯局部润色。

## 推荐的人工处理选项
- 先判断是否保留当前 draft 骨架，再决定局部改或整场重写。
- 直接人工改当前 draft，然后重新运行 reviewer。
- 如果当前 draft 方向已错位，放弃 auto revise，手动重写后再进审稿。
- 优先处理重复未收敛的问题类型：scene_purpose。

## 建议优先查看的文件
- 当前草稿：`02_working/drafts/ch01_scene03_v3_rewrite_v4_rewrite6.md`
- 原任务：`01_inputs/tasks/current_task.md`
- reviewer 原结果：`02_working/reviews/2026-04-03-006-RW6_reviewer.json`
- 结构化 review：`02_working/reviews/2026-04-03-006-RW6_review_result.json`
- repair plan：`02_working/reviews/2026-04-03-006-RW6_repair_plan.json`
- revision lineage：`02_working/reviews/2026-04-03-006_revision_lineage.json`
- 前文基准：`02_working/drafts/ch01_scene03_v3_rewrite_v4_rewrite5.md`
- chapter state：`03_locked/canon/ch01_state.md`

## 下一次重试可直接使用的提示词
- 请基于当前草稿执行一次人工定向修订，而不是自由重写。
- 目标文件：`02_working/drafts/ch01_scene03_v3_rewrite_v4_rewrite6.md`。
- 修订模式：`full_redraft`。
- 必须优先解决以下问题：
- - ISSUE-001 围绕该问题重写相关场段，确保核心目标与约束重新成立。问题：已达到修订阈值 5 轮，建议人工介入。
- - ISSUE-002 围绕该问题重写相关场段，确保核心目标与约束重新成立。问题：当前草稿未充分完成 task 的核心推进目标。
- - ISSUE-003 在对应位置局部改写，直接修复该问题，不扩散到整场。问题：Reviewer 原始输出主要是无效英文分析，已降权处理。
- 不要新增人物、设定或主线扩写；修完后再重新进入 reviewer。

## 次要问题
- Reviewer 原始输出主要是无效英文分析，已降权处理。
