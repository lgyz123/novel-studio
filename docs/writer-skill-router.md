# Writer Skill Router 设计

## 目标

给 `writer` 增加一个稳定、可解释、可调试的 skill 路由层。

这个 router 的职责不是“生成内容”，而是回答：

- 当前这一轮最该加载哪些 skill
- 为什么是这些 skill
- 为什么不是别的 skill
- skill 应该以什么模式注入

---

## 一、设计原则

### 1. Router 决定 skill，不由 writer 自主回忆

`writer` 只消费被选中的 skill。

不要让 `writer` 自己在一个大 skill 库里自由联想，否则会出现：

- 同一任务多次运行选 skill 不一致
- skill 数量越多越不稳定
- 很难 debug “为什么这轮写偏了”

### 2. Router 是轻量判定层，不是第二个 planner

router 不负责：

- 重新规划任务
- 改写 scene contract
- 决定剧情方向

router 只负责：

- 识别需求信号
- 给 skill 打分
- 选出前 1 到 3 个 skill

### 3. Router 输出必须结构化

不要只返回一句“建议使用 naming 和 continuity-guard”。

必须输出：

- phase
- tags
- selected_skills
- reasons
- rejected_candidates
- risk flags

---

## 二、Router 输入

router 的输入建议固定成 6 类。

### 1. `phase`

来自前置状态机。

可选值示例：

- `worldview_bootstrap`
- `timeline_bootstrap`
- `character_creation`
- `chapter_outline`
- `scene_writing`
- `review_repair`

### 2. `task_text`

当前任务单全文。

用于抽取：

- 关键词
- output_target 类型
- scene_purpose
- required_information_gain
- repair_mode

### 3. `planning_assets`

来自 `02_working/planning/` 和 `02_working/outlines/`。

主要包括：

- `worldview_patch.md`
- `timeline_patch.md`
- `character_patch.md`
- `bootstrap_state_machine.md`
- `ch01_outline.md`

### 4. `project_manifest`

来自：

- `00_manifest/novel_manifest.md`
- `00_manifest/world_bible.md`
- `00_manifest/character_bible.md`

用于抽题材和长期约束。

### 5. `state_signals`

来自：

- `03_locked/state/story_state.json`
- `03_locked/state/trackers/*`
- `03_locked/canon/chXX_state.md`

用于判断是否必须上 `continuity-guard`。

### 6. `draft_context`

仅在 `scene_writing` 或 `review_repair` 阶段使用。

例如：

- 当前 draft 是否已存在
- based_on 是否存在
- 是否为 revise / rewrite

---

## 三、Router 输出

建议固定输出如下结构。

```json
{
  "phase": "scene_writing",
  "genre_tags": ["xianxia"],
  "trope_tags": [],
  "demand_tags": ["fight", "continuity", "outline-driven"],
  "selected_skills": [
    {
      "skill": "prose-style",
      "mode": "fight",
      "score": 0.91,
      "reason": "任务明确要求打斗与动作段落描写。"
    },
    {
      "skill": "continuity-guard",
      "mode": "scene-canon",
      "score": 0.88,
      "reason": "当前任务依赖 chapter_state、tracker 和既有 locked scene 承接。"
    }
  ],
  "rejected_candidates": [
    {
      "skill": "naming",
      "score": 0.18,
      "reason": "当前任务没有命名需求。"
    }
  ],
  "risk_flags": [
    "too_many_possible_skills"
  ]
}
```

---

## 四、三层路由逻辑

router 推荐分三层打分。

### 第一层：阶段默认池

先按 `phase` 缩小 skill 候选范围。

#### `worldview_bootstrap`

默认候选：

- `worldbuilding`
- `timeline-history`
- `genre-module/*`
- `trope-module/*`

#### `character_creation`

默认候选：

- `character-design`
- `naming`
- `genre-module/*`
- `trope-module/*`

#### `chapter_outline`

默认候选：

- `scene-outline`
- `timeline-history`
- `worldbuilding`
- `genre-module/*`

#### `scene_writing`

默认候选：

- `prose-style`
- `continuity-guard`
- `scene-outline`
- `character-design`
- `naming`

#### `review_repair`

默认候选：

- `continuity-guard`
- `scene-outline`
- `prose-style`

### 第二层：题材模块加权

从 manifest 中提取题材和母题标签。

#### 题材触发词示例

- `玄幻 / 仙侠 / 修真 / 功法 / 境界 / 宗门` -> `genre-module/xianxia`
- `言情 / cp / 暧昧 / 表白 / 救赎 / he` -> `genre-module/romance`
- `悬疑 / 线索 / 案件 / 惊悚 / 诡案` -> `genre-module/mystery`
- `末世 / 废土 / 生存 / 基地 / 据点` -> `genre-module/post-apoc`
- `种田 / 农事 / 节令 / 家长里短` -> `genre-module/farming`
- `穿越 / 重生 / 快穿 / 异世` -> `genre-module/transmigration`

#### 母题触发词示例

- `abo / alpha / omega / 信息素` -> `trope-module/abo`
- `系统 / 任务 / 面板 / 金手指` -> `trope-module/system`
- `复仇 / 反杀 / 局中局` -> `trope-module/revenge`
- `救赎 / 治愈 / 双向拯救` -> `trope-module/salvation`
- `克苏鲁 / 不可名状 / 古神 / 污染` -> `trope-module/cosmic-horror`

### 第三层：局部需求打分

按 task 和当前上下文的具体需求决定最终 skill。

#### 命名需求

命中词：

- `取名`
- `命名`
- `名字`
- `名称`
- `称号`
- `年号`

加权 skill：

- `naming`

#### 角色需求

命中词：

- `人物设定`
- `角色卡`
- `人物关系`
- `外貌`
- `性格`

加权 skill：

- `character-design`

#### 世界观需求

命中词：

- `世界观`
- `制度`
- `势力`
- `修行`
- `异能`
- `系统规则`

加权 skill：

- `worldbuilding`

#### 时间线需求

命中词：

- `时间线`
- `年代`
- `历史`
- `次日`
- `午后`
- `傍晚`
- `三日前`

加权 skill：

- `timeline-history`

#### 大纲需求

命中词：

- `大纲`
- `scene_purpose`
- `推进`
- `节奏`
- `下一场`

加权 skill：

- `scene-outline`

#### 描写需求

命中词：

- `打斗`
- `感官`
- `氛围`
- `惊悚`
- `情感描写`
- `细节描写`

加权 skill：

- `prose-style`

#### 一致性需求

命中信号：

- 存在 `chapter_state`
- 存在 `story_state`
- 存在 tracker 摘要
- 属于 `revise` / `rewrite`
- 明确提到 `承接 / 一致性 / 物件状态 / 风险等级`

加权 skill：

- `continuity-guard`

---

## 五、评分模型建议

第一版不需要复杂模型，规则打分就够了。

### 基础分

- 命中 phase 默认池：`+0.30`
- 命中 genre/trope：`+0.20`
- 命中局部关键词：每类 `+0.15`
- 命中状态强信号：`+0.20`

### 扣分项

- 与当前 phase 不匹配：`-0.25`
- 已有更直接 skill 覆盖：`-0.15`
- 会和已选 skill 高度重叠：`-0.20`

### 强制规则

- `continuity-guard` 在以下情况强制入选：
  - scene writing 且存在 `chapter_state`
  - repair 阶段
  - 存在 tracker/state 承接要求

- `scene-outline` 在以下情况强制入选：
  - chapter outline 阶段
  - task 含 `scene_purpose / required_information_gain / required_plot_progress`

### 选取上限

- planning 阶段：最多 2 个 skill
- writing 阶段：最多 3 个 skill
- repair 阶段：最多 2 个 skill

---

## 六、注入模式

同一个 skill 可以有不同注入模式。

### `naming`

可选模式：

- `person`
- `place`
- `organization`
- `artifact`
- `technique`

### `character-design`

可选模式：

- `protagonist-card`
- `supporting-role`
- `relationship-tension`

### `worldbuilding`

可选模式：

- `institutional`
- `regional`
- `power-system`

### `timeline-history`

可选模式：

- `world-history`
- `chapter-sequence`
- `scene-bridge`

### `scene-outline`

可选模式：

- `chapter-outline`
- `scene-contract`
- `next-scene-seed`

### `prose-style`

可选模式：

- `fight`
- `emotion`
- `atmosphere`
- `suspense`
- `sensory`

### `continuity-guard`

可选模式：

- `scene-canon`
- `artifact-state`
- `timeline-check`
- `repair-check`

router 不只要选 skill，还要选 mode。

---

## 七、注入顺序建议

技能顺序会影响 writer 的理解重心。

建议顺序：

1. `continuity-guard`
2. `scene-outline`
3. 题材 / 母题 skill
4. 具体能力 skill
5. `prose-style`

原因：

- 先锁边界
- 再锁任务目标
- 再补题材约束
- 最后补写法增强

不要把 `prose-style` 放最前面，否则 writer 很容易只顾文风，不顾 contract。

---

## 八、Fallback 机制

当候选 skill 太多、冲突太强或没有明显命中时，需要 fallback。

### 情况 1：候选太多

处理：

- 保留分数最高的前 3 个
- 其余写入 `rejected_candidates`
- 增加 `risk_flag: too_many_possible_skills`

### 情况 2：没有明显命中

处理：

- planning 阶段默认回退到 `scene-outline` 或 `worldbuilding`
- writing 阶段默认回退到 `continuity-guard`

### 情况 3：skill 互相冲突

例如：

- 同时命中太多 genre/trope

处理：

- 题材优先级高于母题
- 主 genre 高于次 genre
- 只能保留一个主 genre module

---

## 九、与当前代码的接线点

router 最适合接在这几个位置。

### 1. `planning/bootstrap`

在生成：

- `worldview_patch`
- `timeline_patch`
- `character_patch`
- `outline`

前先跑一次 router。

### 2. `compile_context()`

在组装 writer context 时，增加：

- selected skills
- skill reasons
- skill snippets

### 3. `build_writer_user_prompt()`

把 router 结果转成：

- “本轮启用 skill”
- “每个 skill 的 mode”
- “本轮不要启用的能力”

### 4. `reviewer`

后续可增加两个检查：

- 本轮 skill 是否漏选关键能力
- 本轮 skill 是否过载

---

## 十、第一版实现建议

第一版 router 建议只支持这 6 个 skill：

- `naming`
- `character-design`
- `worldbuilding`
- `timeline-history`
- `scene-outline`
- `continuity-guard`

并且先只用规则打分。

第一版不要做：

- 向量检索
- embedding 检索
- 自由 LLM 选 skill
- 复杂多轮 router

先保证可解释、可回放。

---

## 十一、伪代码草案

```python
def route_writer_skills(phase, task_text, manifests, planning_assets, state_signals):
    candidates = candidate_pool_by_phase(phase)
    scores = {skill: 0.0 for skill in candidates}

    for skill in candidates:
        scores[skill] += phase_score(skill, phase)
        scores[skill] += genre_score(skill, manifests, task_text)
        scores[skill] += keyword_score(skill, task_text)
        scores[skill] += state_score(skill, state_signals)
        scores[skill] -= overlap_penalty(skill, scores)

    selected = apply_forced_rules(scores, phase, state_signals)
    selected = top_k(selected, k=phase_limit(phase))
    return build_router_result(selected, scores)
```

---

## 十二、成功标准

router 是否合格，可以看 4 个指标。

### 1. 稳定性

同一个 task 多次运行，选 skill 基本一致。

### 2. 可解释性

看结果能明确知道为什么选它。

### 3. 节制

大多数轮次不超过 3 个 skill。

### 4. 实用性

被选中的 skill 真的能改善 planning 或 writer 输出，而不是装饰。

---

## 十三、下一步

下一步最合理的是给第一批 6 个 skill 写 spec：

- 输入
- 输出
- mode
- 边界
- 示例

这部分放在：

- `docs/skills-first-batch.md`

定下来以后，再决定先把它们做成文档 skill，还是直接做成真实 skill 目录。
