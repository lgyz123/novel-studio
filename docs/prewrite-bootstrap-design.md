# 写前补全层设计整理

## 当前项目现状

这个仓库当前已经具备一条比较完整的 scene 级流水线：

1. 任务文件定义单场写作目标
2. `writer` 生成草稿
3. `reviewer` / `lock_gate` / `supervisor` 做修订与锁定
4. `story_state` 与 chapter tracker 在锁定后回填正典状态

它擅长的是“已有任务后的写作控制”，不擅长“写作前先把世界观、时间线、角色、大纲补齐”。

## 这次梳理发现的关键缺口

### 1. 缺少写前 planning/bootstrap 层

当前 `app/main.py` 会直接读取 `01_inputs/tasks/current_task.md` 并开始 scene 写作。
这意味着系统默认：

- 世界观已经足够完整
- 时间线已经足够清晰
- 角色设定已经足够可写
- 大纲和章节目标已经先验存在

这和“先 review，不足自动补足，再进入写作”的需求不一致。

### 2. 世界观文档偏原则，缺少可写的闭环

`00_manifest/world_bible.md` 目前更像主题约束和方向说明，强项在：

- 社会结构方向明确
- 修行逻辑方向明确
- 天道风格明确

但弱项也很明显：

- 缺少世界异常事物的生态位推演
- 缺少主要舞台的空间层次
- 缺少历史节点年表
- 缺少“制度如何具体应对异常”的链条

### 3. 时间线只有锁后 state，没有写前时间策划层

当前只有：

- `00_manifest/novel_manifest.md` 的卷级长线
- `03_locked/state/story_state.json` 的近期事件
- `03_locked/canon/ch01_state.md` 的章节状态

但没有独立的时间线资产，例如：

- 世界历史时间线
- 本卷时间线
- 本章时间线
- 当前场和上一场之间的明确时间关系

### 4. writer prompt 现在要求“资料不足不要硬补设定”

这条规则对 scene 稳定性是好的，但它和“自动补足世界观/时间线”之间有天然冲突。
如果没有单独的写前补全步骤，writer 只能停在保守写法，无法主动填坑。

### 5. 当前上下文裁剪对世界观/时间线不够友好

`compile_context()` 目前会裁剪：

- `novel_manifest.md`
- `world_bible.md`
- `chapter_state`

这对 scene 写作足够，但对“写前做全局 review”还不够，因为缺少面向缺口的结构化摘要。

## 已落地的第一步改动

这次先补了一层低风险的 deterministic 写前诊断：

- 新增 [app/prewrite_checks.py](/Users/guan/git/novel-studio/app/prewrite_checks.py)
- 在 [app/main.py](/Users/guan/git/novel-studio/app/main.py) 的 `compile_context()` 中接入写前诊断
- 新增测试 [tests/test_prewrite_checks.py](/Users/guan/git/novel-studio/tests/test_prewrite_checks.py)

### 当前新行为

每次编译 writer 上下文时，会先生成：

- `02_working/context/prewrite_review.md`

里面会先检查两件事：

1. 世界观是否缺少核心法则、生态位/社会应对、时空舞台、历史变迁、核心矛盾闭环
2. 时间线是否缺少长线骨架、历史事件锚点、当前剧情时点、近期正典事件

然后把这份“写前诊断”插入 writer context 顶部，让写作前至少先看到缺口。

## 这层能力还没有完成的部分

这次接入的是“review + 标出待补区域”，还不是完整的“自动补全后回写正典”。

缺的能力主要有三段：

### 1. 模型驱动的补全草案生成

建议新增一个 `planner` 或 `bootstrap` agent，专门输出：

- 世界观补全草案
- 时间线补全草案
- 角色补全草案
- 章节大纲草案

这些内容先落到 `02_working/`，不要直接写进 `00_manifest/` 或 `03_locked/`。

### 2. proposal 到 canon 的审批/合并机制

建议新增 working 区资产，例如：

- `02_working/planning/worldview_patch.md`
- `02_working/planning/timeline_patch.md`
- `02_working/planning/character_patch.md`
- `02_working/outlines/ch01_outline.md`

再增加一个人工确认或规则确认环节，决定哪些补全进入长期 canon。

### 3. 新的总流程

建议把主流程抬成：

1. 写前诊断世界观
2. 写前诊断时间线
3. 如不足则生成补全 proposal
4. 基于 proposal 生成角色卡 / 章节大纲
5. 再开始具体 scene 写作
6. scene 锁定后继续更新 state 与 tracker

## 最适合继续做的下一步

### 方案 A：先补“世界观/时间线补全 proposal”

这是最稳妥的一步。目标是让系统在写前不只是报缺口，还能生成候选补全文本。

优点：

- 对现有 scene 流程侵入小
- 风险低
- 立刻能提升写前准备质量

### 方案 B：新增 chapter-level outline 层

先让系统在 scene 之前自动产出章节大纲、关键锚点和角色弧光。

优点：

- 更贴近“先有纲再写章”
- 能直接改善后续任务生成质量

代价：

- 要调整 supervisor 的 next-scene planning 逻辑

### 方案 C：做完整四步式前置流水线

即用户描述的：

1. 世界观构建
2. 角色创建
3. 大纲定制
4. 第一章撰写

优点：

- 用户体验最完整
- 最接近产品化形态

代价：

- 需要新增多个 prompt、schema、工作目录和状态机
- 需要重新定义当前 `current_task.md` 的职责

## 我对当前仓库的判断

这个项目的底座已经不差，尤其 scene 审稿、锁定和状态回填这部分已经成型。
真正短板不是“写不好某一场”，而是“写之前缺少一层策划型状态机”。

所以最合理的演进方向不是继续堆 writer prompt，而是补一个前置 planning 层，让：

- manifest 成为长期 canon
- planning proposal 成为写前补全资产
- task 只负责具体执行
- story_state / tracker 继续负责锁后事实更新
