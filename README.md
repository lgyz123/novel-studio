# novel-studio

## 项目简介
`novel-studio` 是一个以文件系统为中心的中文小说自动写作流水线原型。它目前已经不只是“单 Agent 写稿”，而是演进成了一个带有多阶段质量控制的本地工作流：

- `writer` 负责产出正文草稿
- `reviewer` 负责结构化审稿与本地规则兜底
- `supervisor` 负责在卡住时决定继续修、重写、救场或为下一 scene 生成任务
- `lock gate` 负责在锁定前做最终硬检查
- `story_state` 与 `chapter_trackers` 负责在锁定后更新正典状态与章节级 tracker

整个系统不依赖数据库，所有中间状态都保存在目录结构中，因此非常适合调试、回放、重建状态和做局部迭代。

## 当前工作流概览
当前主流程可以概括为：

1. 从 `01_inputs/tasks/current_task.md` 读取当前任务
2. `writer` 生成草稿，输出到 `02_working/drafts/`
3. `reviewer` 输出结构化审稿结果到 `02_working/reviews/`
4. 本地 guardrail 与 `lock gate` 决定：`lock / revise / rewrite`
5. 如多轮修订仍失败，`supervisor` 会介入，决定继续修、整体重写、救场或人工中断
6. 如果 `lock`：
	 - 正文写入 `03_locked/chapters/`
	 - notes / proposal / report 写入 `03_locked/` 与 `02_working/`
	 - `story_state` 更新到 `03_locked/state/story_state.json`
	 - chapter tracker 更新到 `03_locked/state/trackers/`
	 - `supervisor` 可为下一 scene 自动生成任务草案

## 目录结构
### 顶层目录
- `00_manifest/`：总纲、设定、人物资料、长期不常变的世界观材料
- `01_inputs/`：当前任务、参考材料、生活素材
- `02_working/`：草稿、审稿结果、上下文、临时提案、日志
- `03_locked/`：已锁定正文、正典 notes、状态快照、报告与 tracker
- `app/`：主程序和全部核心规则实现
- `prompts/`：writer / reviewer 的提示词、schema 与约束模板
- `tests/`：当前主要回归测试
- `docs/`：额外设计文档与后续计划

### `01_inputs/`
- `tasks/`：当前任务与 supervisor 生成的后续任务
- `life_notes/`：生活观察或素材片段
- `references/`：写作参考资料

### `02_working/`
- `context/`：当前上下文拼装结果
- `drafts/`：writer 当前工作草稿
- `reviews/`：reviewer / supervisor 输出 JSON
- `canon_updates/`：notes、state、tracker 等工作中提案
- `logs/`：失败稿、失败原因、调试痕迹
- `outlines/`：工作期大纲或临时结构稿
- `test_artifacts/`：测试生成的临时产物

### `03_locked/`
- `chapters/`：正式锁定的 scene 正文
- `candidates/`：锁定时保留的 candidate 副本
- `canon/`：章节状态、锁定 notes 等正典文本
- `reports/`：lock gate 报告等结构报告
- `state/`：长期状态文件
	- `story_state.json`：跨章节 story state
	- `history/`：每次 lock 的 state diff 和 snapshot
	- `trackers/`：章节级 tracker，如 motif / revelation / artifact / progress

## 核心模块地图
### 入口与编排
- `app/main.py`：主流程编排入口，负责写作、审稿、修订分支、锁定、状态落盘、下场任务生成
- `app/config.yaml`：模型、目录、超时、自动修订轮数等配置

### 审稿与修订控制
- `app/review_scene.py`：reviewer 接入、本地结构检查、guardrail 兜底、结果归一化
- `app/review_models.py`：结构化审稿数据模型与 repair plan 保存
- `app/lock_gate.py`：锁定前的最终硬检查
- `app/revision_lineage.py`：修订链路、轮次控制、人工介入阈值
- `app/issue_filters.py`：问题列表去噪与去重

### Supervisor / DeepSeek 层
- `app/deepseek_supervisor.py`：supervisor 决策、救场、下一 scene 任务规划
- `app/deepseek_reviewer.py`：DeepSeek reviewer 接口封装

### 状态与 tracker
- `app/story_state.py`：跨场景 `story_state` 更新、diff、rebuild
- `app/chapter_trackers.py`：章节级动态 tracker
	- `chapter_motif_tracker`
	- `revelation_tracker`
	- `artifact_state`
	- `chapter_progress`

### 辅助脚本
- `app/rebuild_story_state.py`：基于 locked 文件重建 `story_state`
- `app/set_current_task.py`：切换当前任务
- `app/smoke_test_runner.py` 与 `app/run_five_scene_smoke_test.py`：烟雾测试工具

## 当前已经具备的能力
截至目前，这个原型已经具备以下比较完整的能力：

- **结构化审稿**：不仅判断好不好，还会落到 `information_gain / plot_progress / character_decision / motif_redundancy / canon_consistency`
- **本地 deterministic guardrail**：即使 reviewer 输出不稳定，也有本地规则兜底
- **Supervisor 介入**：当 revise/rewrite 多轮不收敛时，supervisor 会决定继续修、重写、救场或转人工
- **下一场任务规划**：supervisor 可以根据章节进度与 tracker 为下一场自动生成任务草案
- **章节级 tracker**：motif / revelation / artifact / progress 已改成动态 chapter-scoped tracker，而不是全局硬编码词表
- **锁后状态落盘**：只有在 `lock` 后才会把 `story_state` 与 tracker 的实际更新写入正典状态
- **状态重建**：可以从 `03_locked/chapters/` 反推重建 `story_state`
- **测试覆盖**：已有 reviewer / supervisor / lock gate / story_state / revision lineage 等回归测试

## 当前架构上的几个关键设计点
### 1. 文件流而不是数据库
所有中间产物可见、可 diff、可手工修正，适合小说流水线这种需要频繁 debug 的场景。

### 2. 锁定才算“进入正典”
`02_working/` 里的内容都只是候选；只有通过 `lock gate` 并写入 `03_locked/` 的内容才算正式状态。

### 3. tracker 和 story state 分层
- `story_state` 更偏全局长期状态
- `chapter_trackers` 更偏章节级推进控制

这种分层便于后续把“章节内控制”和“跨章节连续性”拆开演进。

### 4. 规则和模型协同
不是完全依赖大模型判断，而是让模型负责生成/分析，让本地规则负责底线约束。

## 测试结构
当前测试主要集中在：

- `tests/test_review_scene.py`：reviewer 本地规则、guardrail、结果归一化
- `tests/test_deepseek_supervisor.py`：supervisor 决策、救场、下一场任务规划
- `tests/test_lock_gate.py`：锁定门槛检查
- `tests/test_story_state.py`：state 更新、patch、重建
- `tests/test_review_models.py`：结构化审稿模型与 repair plan
- `tests/test_revision_lineage.py`：修订链与人工介入路径
- `tests/test_deepseek_reviewer.py`：DeepSeek reviewer 侧行为
- `tests/test_smoke_test_runner.py`：烟雾测试执行器

## 适合你接下来继续思考的改造方向
如果你准备继续加功能，当前比较自然的扩展方向有：

- **多角色状态层**：现在 `story_state` 仍以 `protagonist` 单槽为主，可扩成多角色 profile
- **章节规划层**：把 `supervisor` 的 scene planning 再往 chapter outline 层提高一级
- **更强的 canon diff**：目前已有 state/tracker diff，后续可以增加更可读的 narrative diff
- **更强的人工介入接口**：例如人工批准/拒绝某个 tracker proposal 或某场 lock
- **更稳定的 smoke test 场景集**：为不同题材/不同章节节奏准备固定回归样本

## 如何运行
### 本地运行
1. 创建虚拟环境：`python3 -m venv app/.venv`
2. 激活虚拟环境：
	 - macOS / Linux：`source app/.venv/bin/activate`
	 - Windows PowerShell：`./app/.venv/Scripts/Activate.ps1`
3. 安装依赖：`pip install -r app/requirements.txt`
4. 运行主程序：`python app/main.py`

### 当前项目环境提示
如果你在当前仓库里继续开发，现有工作环境实际已经使用仓库外层虚拟环境，例如：`/Users/guan/git/.venv/bin/python`。

### Codespaces
- 仓库已提供 `.devcontainer/` 配置
- 首次创建 Codespace 时会自动：
	- 创建 `app/.venv`
	- 安装 `app/requirements.txt`
	- 为终端自动激活 `app/.venv`

## Git 使用建议
- 建议每次大改前先 commit
- `02_working/logs/` 下日志文件已自动忽略
- 不要将敏感信息提交到仓库
