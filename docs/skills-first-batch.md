# 第一批 Writer Skills 规格

## 目标

定义第一批最值得落地的 6 个 writer skill。

这批 skill 的标准不是“最炫”，而是：

- 和当前流水线最贴近
- 最容易接入 planning/bootstrap
- 最容易验证成效
- 最能提升稳定性

第一批 skill：

1. `naming`
2. `character-design`
3. `worldbuilding`
4. `timeline-history`
5. `scene-outline`
6. `continuity-guard`

---

## 一、`naming`

### 作用

统一处理各种命名任务。

### 适用场景

- 人名
- 地名
- 势力名
- 店铺名
- 法器名
- 招式名
- 年号 / 朝代号

### 不适用场景

- 需要完整角色卡
- 需要组织设定或制度说明
- 需要正文描写增强

### 输入

- `name_type`
- `genre_tags`
- `tone`
- `era_style`
- `region_hint`
- `gender_hint`
- `class_hint`
- `canon_blacklist`

### 输出格式

```json
{
  "skill": "naming",
  "mode": "person",
  "candidates": [
    {
      "name": "孟浮灯",
      "style_tags": ["古风", "冷感", "底层"],
      "meaning_or_feel": "有漂泊与微弱光感",
      "fit_for": "主角"
    }
  ]
}
```

### 硬约束

- 不得和现有 canon 撞名
- 不得出现明显现代互联网式命名
- 不得只给生僻字炫技型名字
- 要能解释风格与适配角色

### 推荐 mode

- `person`
- `place`
- `organization`
- `artifact`
- `technique`

### 成功标准

- 候选名可直接落入设定
- 风格一致
- 有区分度但不过度花哨

---

## 二、`character-design`

### 作用

产出角色功能卡，而不是无边界人物小传。

### 适用场景

- 主角角色卡
- 配角功能卡
- 关系张力
- 外貌与行为锚点

### 不适用场景

- 写世界观制度
- 生成 scene 大纲
- 做纯 prose 描写增强

### 输入

- `role_type`
- `plot_function`
- `relationship_target`
- `genre_tags`
- `trope_tags`
- `existing_character_notes`

### 输出格式

```json
{
  "skill": "character-design",
  "mode": "supporting-role",
  "card": {
    "core_drive": "求稳避险",
    "external_function": "提供低烈度阻力",
    "behavior_markers": ["说话收着", "先看人脸色再答"],
    "speech_tendency": "短句，偏试探",
    "tension_with_protagonist": "他让主角更难直接问出口"
  }
}
```

### 硬约束

- 先给“功能”，再给“背景”
- 不得把配角写成喧宾夺主的第二主角
- 行为锚点必须能落到 scene 动作里
- 不能和既有角色设定冲突

### 推荐 mode

- `protagonist-card`
- `supporting-role`
- `relationship-tension`

### 成功标准

- 角色卡能直接指导 writer 写动作与对话
- 不只是抽象性格词

---

## 三、`worldbuilding`

### 作用

输出写前补全 proposal，补的是“可写性”而不是百科。

### 适用场景

- 世界观补全
- 制度链条补全
- 修行 / 异能 / 系统规则补丁
- 空间舞台补丁

### 不适用场景

- 直接细写正文
- 替代章节大纲

### 输入

- `world_review`
- `genre_tags`
- `trope_tags`
- `manifest_excerpt`
- `state_constraints`

### 输出格式

```json
{
  "skill": "worldbuilding",
  "mode": "institutional",
  "gaps": ["生态位与社会应对"],
  "patches": [
    "补出异常事物如何进入民间日常处置链。",
    "说明官面与民间对同一风险的不同反应。"
  ],
  "writer_usable_hooks": [
    "可以在货栈、运河、守夜、收尸等岗位中体现制度压力。"
  ]
}
```

### 硬约束

- 必须回扣现有 manifest
- 不得另起一套体系
- 优先补制度、代价、空间、行动限制
- 不得为了“丰富世界”偷渡新主线

### 推荐 mode

- `institutional`
- `regional`
- `power-system`

### 成功标准

- 补丁能直接服务 scene 写作
- reader 不看补丁也能从正文中感到世界更扎实

---

## 四、`timeline-history`

### 作用

统一处理历史锚点与场景时间承接。

### 适用场景

- 世界历史年表
- 卷级时间线
- 章节承接
- scene 与上一场的时间桥接

### 不适用场景

- 生成人名地名
- 直接写世界制度

### 输入

- `timeline_review`
- `chapter_state_excerpt`
- `story_state_timeline`
- `task_time_markers`

### 输出格式

```json
{
  "skill": "timeline-history",
  "mode": "scene-bridge",
  "current_time": "次日清早",
  "relative_order": [
    "上一场发生在夜里",
    "本场与上一场相隔一夜"
  ],
  "history_anchors": [
    "旧制成形",
    "一次大灾后加重差役"
  ],
  "timeline_risks": [
    "如果不写明白天，读者会误以为还在同一夜"
  ]
}
```

### 硬约束

- 优先明确相对时序
- 要标出漂移风险
- 不得和 `story_state.timeline` 打架

### 推荐 mode

- `world-history`
- `chapter-sequence`
- `scene-bridge`

### 成功标准

- scene 与 scene 之间的时间关系更清晰
- reviewer 更少打出时间线问题

---

## 五、`scene-outline`

### 作用

给章节与场景提供结构骨架。

### 适用场景

- 章节 outline
- scene contract 补全
- 下一场任务种子

### 不适用场景

- 纯命名
- 纯世界观设定
- 纯 prose 风格增强

### 输入

- `goal`
- `scene_purpose`
- `required_information_gain`
- `required_plot_progress`
- `required_decision_shift`
- `required_state_change`
- `recent_scene_summaries`

### 输出格式

```json
{
  "skill": "scene-outline",
  "mode": "scene-contract",
  "scene_function": "引入外部阻力",
  "must_land": {
    "new_information": ["确认新风险条件"],
    "plot_progress": "阻碍升级",
    "decision_shift": "主角改变处理方式",
    "state_change": ["风险等级变化"]
  },
  "ending_shape": "结尾必须比开头多一个现实后果"
}
```

### 硬约束

- 只定义结构目标，不写长 prose
- 必须和现有 task contract 对齐
- 不得越权改写项目主线

### 推荐 mode

- `chapter-outline`
- `scene-contract`
- `next-scene-seed`

### 成功标准

- writer 更容易交出新信息、新动作、新后果
- reviewer 的“推进不足”问题下降

---

## 六、`continuity-guard`

### 作用

这是第一批里最关键的 guard skill。

它负责把 writer 输出压回 canon 和 tracker 约束里。

### 适用场景

- scene 写作
- revise / rewrite
- 连续场景承接
- 物件状态 / 风险等级 / 关系态势检查

### 不适用场景

- 自由脑暴
- 风格增强
- 题材扩写

### 输入

- `chapter_state`
- `story_state`
- `tracker_bundle`
- `recent_scene_summaries`
- `current_task`

### 输出格式

```json
{
  "skill": "continuity-guard",
  "mode": "scene-canon",
  "must_check": [
    "主角当前模式",
    "调查阶段",
    "风险等级",
    "关键物件位置"
  ],
  "high_risk_conflicts": [
    "不要把已贴身保留的物件重新写回盒中"
  ],
  "non_drift_fields": [
    "last known artifact holder",
    "current book time",
    "investigation stage"
  ]
}
```

### 硬约束

- 不生成新创意
- 只做约束、核对、拦错
- repair 阶段优先级最高
- 发现高风险冲突时要明确阻止 writer 漂移

### 推荐 mode

- `scene-canon`
- `artifact-state`
- `timeline-check`
- `repair-check`

### 成功标准

- canon consistency 问题明显下降
- 修订轮次减少

---

## 七、第一批接入顺序

建议按这个顺序落地。

### 第一步：只做 planning 用 skill

- `worldbuilding`
- `timeline-history`
- `character-design`
- `scene-outline`

接入：

- `planning/bootstrap`
- `chapter outline`

### 第二步：给 writer 接保护型 skill

- `continuity-guard`

这是优先级最高的 writer skill，因为它最能降低写偏概率。

### 第三步：补 writer 增强型 skill

- `naming`
- `prose-style`

其中 `prose-style` 可以先只做文档 spec，放到第二批落地。

---

## 八、建议的 skill 目录命名

建议后续 skill 目录按这个命名：

```text
skills/
  naming/
  character-design/
  worldbuilding/
  timeline-history/
  scene-outline/
  continuity-guard/
```

如果要先做文档版，也建议保持同名，后续迁移最省事。

---

## 九、每个 Skill 的验证方式

### `naming`

验证点：

- 候选名不撞 canon
- 风格标签可信
- 命名和题材匹配

### `character-design`

验证点：

- 输出的行为锚点是否能写进 scene
- 功能是否清楚

### `worldbuilding`

验证点：

- 补丁是否真的服务写作
- 是否偷渡新主线

### `timeline-history`

验证点：

- 是否明确当前时段
- 是否指出承接漂移风险

### `scene-outline`

验证点：

- 是否把 contract 说清楚
- 是否能约束 writer 交出新变化

### `continuity-guard`

验证点：

- 是否能抓到 artifact / timeline / risk / relationship 漂移

---

## 十、下一步

下一步最合理的是二选一：

1. 开始把这 6 个 skill 做成真正的 skill 目录
2. 先写 `writer-skill-router` 的代码设计稿，再决定怎么在 `compile_context()` 或 `build_writer_user_prompt()` 中接入

如果以“最小可用增量”为目标，建议先做：

- `continuity-guard`
- `scene-outline`
- `worldbuilding`

这三个最容易直接改善当前流水线。
