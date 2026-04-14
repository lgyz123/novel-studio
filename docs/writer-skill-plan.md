# Writer Skill 规划

## 目标

给 `writer` 增加一层可控的 skill 机制，但不让 skill 库失控膨胀，也不让 `writer` 在上下文里自己盲选。

设计目标：

- skill 要按“能力域”组织，而不是按页面按钮逐条复制
- skill 选择要可路由、可解释、可回放
- skill 输出要能接入现有 `planning/bootstrap -> writer -> reviewer -> lock` 流程
- 第一版优先解决“世界观补全、角色创建、大纲定制、正文写作承接、一致性校验”

---

## 一、总原则

### 1. 不按按钮一比一做 skill

截图里的词条很多是 UI 入口，不是稳定的 skill 边界。

例如：

- `古风姓名`
- `女风取名`
- `武侠仙侠人名`
- `门派势力名称`

这些都不应该拆成四个独立 skill，而应归到同一个 `naming` 能力域下，用不同子模式处理。

### 2. 先路由，再注入，不让 writer 自由全库搜索

推荐流程：

1. 读取 `task + planning assets + current context`
2. 提取需求信号
3. 由 `skill_router` 选出 1 到 3 个 skill
4. 只把命中的 skill 注入 writer context
5. writer 按注入 skill 生成内容

不要让 writer 自己“想起某个 skill 就用”，否则：

- 不稳定
- 不可回放
- 难调试
- skill 数量一多就会严重抢上下文

### 3. 先做大 skill，再做子 skill

第一版先做“一级 taxonomy”，等路由稳定后再细分子 skill。

---

## 二、一级 Skill Taxonomy

建议先定义 10 个一级 skill。

### 1. `naming`

负责：

- 人名
- 地名
- 势力名
- 法器名
- 招式名
- 年号 / 朝代号 / 店铺号

可覆盖截图中的：

- 古风姓名
- 女风取名
- 武侠仙侠人名
- 门派势力名称
- 组织势力取名
- 技能招式取名
- 地点场景取名
- 小说架空朝代年号

### 2. `character-design`

负责：

- 主角 / 配角角色卡
- 外貌锚点
- 性格动作习惯
- 关系张力
- 角色功能槽位

可覆盖：

- 人物设定
- 人物描写
- 外貌描写
- 性格描写
- CP 角色设定
- 娱乐圈人物设定
- 年代文人物设定

### 3. `worldbuilding`

负责：

- 世界观骨架
- 制度链条
- 空间舞台
- 组织结构
- 修行 / 异能 / 系统规则

可覆盖：

- 世界架构设定
- 世界观构建设定
- 势力组织架构
- 修真境界解析
- 修真功法解析
- 系统设定
- 异能超能力

### 4. `timeline-history`

负责：

- 世界历史节点
- 年代背景
- 本卷 / 本章时间线
- 当前 scene 时间承接

可覆盖：

- 年代文背景设定
- 年代文情节设定
- 年代历史票证常识
- 干支纪年转换
- 时辰对照

### 5. `scene-outline`

负责：

- 章节大纲
- scene contract
- 冲突布点
- 节奏与推进
- 下一场任务种子

可覆盖：

- 剧情创作
- 情节设定
- 情节片段描写
- 攻略任务生成器
- 悬疑诡案及线索设计

### 6. `prose-style`

负责：

- 打斗描写
- 感官描写
- 景物 / 环境 / 氛围描写
- 情感描写
- 惊悚 / 恐怖 / 悬疑氛围

可覆盖：

- 打斗描写
- 细节描写
- 感官描写
- 环境 / 场景描写
- 情感描写
- 惊悚感描写
- 大气场景描写

### 7. `genre-module`

负责题材级约束，不直接产正文，而是提供题材 guardrails。

建议先做这些子模块：

- `genre-module/xianxia`
- `genre-module/romance`
- `genre-module/mystery`
- `genre-module/post-apoc`
- `genre-module/farming`
- `genre-module/transmigration`

### 8. `trope-module`

负责母题级约束与模板，不直接替代人物或世界观。

建议先做这些子模块：

- `trope-module/abo`
- `trope-module/system`
- `trope-module/revenge`
- `trope-module/salvation`
- `trope-module/cosmic-horror`

### 9. `continuity-guard`

负责：

- 人设一致性
- 时间线一致性
- 物件状态一致性
- 风险等级 / 关系态势一致性
- 与 `story_state` / `trackers` 对齐

这是 writer 与 reviewer 之间最关键的桥。

### 10. `research-tables`

负责资料型辅助表：

- 古代物价
- 农具 / 作物 / 节令
- 职业称谓
- 礼俗 / 衣食住行
- 年代票证 / 工资 / 店铺

这种 skill 更适合输出“参考表”或“约束表”，而不是直接帮 writer 写正文。

---

## 三、Skill 选择机制

最重要的不是 skill 本身，而是 `怎么选 skill`。

建议采用三层路由。

### 第一层：按阶段选

按当前前置状态机阶段，决定默认 skill 池。

#### 世界观补全

优先：

- `worldbuilding`
- `timeline-history`

候补：

- `genre-module/*`
- `trope-module/*`

#### 角色创建

优先：

- `character-design`
- `naming`

候补：

- `genre-module/*`
- `trope-module/*`

#### 大纲定制

优先：

- `scene-outline`
- `timeline-history`

候补：

- `worldbuilding`
- `genre-module/*`

#### 第一章撰写 / scene 写作

优先：

- `prose-style`
- `continuity-guard`

候补：

- `character-design`
- `scene-outline`

### 第二层：按题材选

从 `novel_manifest / world_bible / task` 中抽取题材标签。

例如：

- 出现 `玄幻 / 仙侠 / 修真 / 功法 / 境界` -> `genre-module/xianxia`
- 出现 `言情 / cp / 表白 / 暧昧 / 救赎` -> `genre-module/romance`
- 出现 `悬疑 / 线索 / 案件 / 惊悚` -> `genre-module/mystery`
- 出现 `末世 / 废土 / 生存 / 组织据点` -> `genre-module/post-apoc`
- 出现 `种田 / 农事 / 节令 / 家长里短` -> `genre-module/farming`
- 出现 `穿越 / 重生 / 系统 / 快穿` -> 对应 `genre-module` 或 `trope-module`

### 第三层：按局部需求触发

再用 task 关键词决定局部 skill。

#### 触发词建议

- `取名 / 名字 / 名称 / 命名` -> `naming`
- `人物设定 / 角色卡 / 人设 / 关系` -> `character-design`
- `世界观 / 制度 / 势力 / 地域 / 修行 / 系统规则` -> `worldbuilding`
- `时间线 / 年代 / 历史 / 次日 / 傍晚 / 三日前` -> `timeline-history`
- `大纲 / 节奏 / 推进 / scene_purpose / 下一场` -> `scene-outline`
- `描写 / 打斗 / 感官 / 情感 / 惊悚 / 气氛` -> `prose-style`
- `一致性 / 承接 / canon / story_state / tracker / 物件状态` -> `continuity-guard`
- `物价 / 农具 / 礼俗 / 票证 / 职业 / 常识` -> `research-tables`

---

## 四、路由输出格式建议

不要只输出 skill 名称，建议输出结构化选择结果。

示例：

```json
{
  "phase": "chapter_outline",
  "genre_tags": ["xianxia"],
  "trope_tags": [],
  "selected_skills": [
    {
      "skill": "scene-outline",
      "reason": "当前任务要求生成章节与场景级推进骨架。"
    },
    {
      "skill": "timeline-history",
      "reason": "任务需要明确本章与上一场的时间承接。"
    },
    {
      "skill": "genre-module/xianxia",
      "reason": "项目 manifest 明确为玄幻/仙侠题材。"
    }
  ],
  "rejected_candidates": [
    {
      "skill": "naming",
      "reason": "本轮没有命名型任务。"
    }
  ]
}
```

这样有三个好处：

- 可调试
- 可回放
- reviewer 能复查 skill 选得对不对

---

## 五、每个 Skill 的最小规范

每个 skill 建议固定 5 块。

### 1. 适用场景

什么时候用，什么时候不要用。

### 2. 输入信号

从哪些字段触发：

- task keywords
- phase
- genre tags
- tracker signals

### 3. 输出格式

输出必须稳定，不能太散。

例如：

- 命名 skill 输出候选列表
- worldbuilding skill 输出补丁条目
- prose-style skill 输出写法规则和正反例
- continuity skill 输出核对清单

### 4. 硬约束

例如：

- 不得与 canon 冲突
- 不得引入现代词
- 不得偷渡新主线
- 不得把 skill 当成自由扩写理由

### 5. few-shot / 模板

只给真正必要的例子，不要太多。

---

## 六、第一批最值得做的 Skill

建议先做 6 个。

### `naming`

用途：

- 一切命名任务统一收口

输出建议：

- `name`
- `type`
- `style_tags`
- `meaning_or_feel`
- `fit_for`

为什么优先：

- 需求高频
- 结构清晰
- 容易验证

### `character-design`

用途：

- 角色卡
- 功能卡
- 关系张力

输出建议：

- 核心驱动力
- 外部功能
- 常见动作
- 语言倾向
- 与主角的张力点

### `worldbuilding`

用途：

- 写前补全 proposal
- 制度链条补丁

输出建议：

- 缺口
- 补丁提议
- 与现有设定的衔接
- 正文可调用点

### `timeline-history`

用途：

- 章级 / 场级时间承接
- 历史锚点补全

输出建议：

- 当前时段
- 相对时序
- 历史锚点
- 时间承接风险

### `scene-outline`

用途：

- 章节 outline
- scene contract
- next scene seeds

输出建议：

- 场景功能
- 新信息
- 推进要求
- 决策偏移
- 结尾状态变化

### `continuity-guard`

用途：

- 防止 writer 因 skill 加强而偷渡设定或破坏 canon

输出建议：

- 本轮必须核对项
- 高风险冲突项
- 不允许漂移的状态项

---

## 七、每类 Skill 的边界

这是最容易失控的地方。

### `prose-style` 不负责

- 发明新设定
- 推进主线
- 修改时间线

它只负责“怎么写更好”。

### `worldbuilding` 不负责

- 直接决定正文该写哪一场

它只负责“这个世界缺什么、该补什么”。

### `scene-outline` 不负责

- 细写 prose

它只负责“这一场该完成什么”。

### `naming` 不负责

- 改写人物命运或设定

它只负责生成名称候选。

### `continuity-guard` 不负责

- 产出新创意

它只负责约束、比对、拦错。

---

## 八、如何把 Skill 接进当前流水线

建议分三步。

### 第一步：只做 planning 阶段 skill

先接入：

- `worldbuilding`
- `timeline-history`
- `character-design`
- `scene-outline`

接入点：

- `planning/bootstrap`
- `chapter outline`
- `next scene planning`

这是低风险区，因为它们主要产 proposal，不直接写正文。

### 第二步：给 writer 接只读 skill 注入

先接入：

- `continuity-guard`
- `prose-style`
- `naming`

规则：

- writer 每轮最多加载 3 个 skill
- 每个 skill 只加载必要部分
- skill 输出优先是约束与模板，不是长文解释

### 第三步：让 reviewer 回看 skill 选择是否合理

reviewer 可以增加两项检查：

- 本轮 skill 是否选多了
- 本轮是否漏选关键 skill

这样 skill 机制才能闭环。

---

## 九、建议的目录与文件

如果后续正式实现本地 skill，建议用下面的命名方式。

```text
skills/
  writer-skill-router/
  naming/
  character-design/
  worldbuilding/
  timeline-history/
  scene-outline/
  prose-style/
  continuity-guard/
  genre-module/
    xianxia/
    romance/
    mystery/
    post-apoc/
    farming/
    transmigration/
  trope-module/
    abo/
    system/
    revenge/
    salvation/
    cosmic-horror/
  research-tables/
```

第一版甚至不需要所有 skill 都是完整 skill 目录，也可以先做：

- 一个 `writer-skill-router` 设计稿
- 几个 skill spec 文档

---

## 十、第一批实施顺序

推荐顺序：

1. `docs/writer-skill-plan.md`
2. `docs/writer-skill-router.md`
3. `docs/skills/naming.md`
4. `docs/skills/worldbuilding.md`
5. `docs/skills/scene-outline.md`
6. `docs/skills/continuity-guard.md`
7. 再把它们真正变成 skill 目录

原因：

- 先把规则定住
- 再做 skill 本体
- 最后接代码

---

## 十一、对 skill 选择的具体建议

如果只说一句最重要的建议，那就是：

**skill 不应该由 writer 自主“想起”，而应该由 router 根据阶段、题材、关键词和状态信号选出来。**

具体落地上，建议采用：

- `phase` 决定默认 skill 池
- `genre_tags` 决定题材模块
- `task keywords` 决定局部能力 skill
- `story_state / tracker` 决定是否必须加 `continuity-guard`

同时加两个硬限制：

- 一轮最多 3 个 skill
- 任一 skill 都不能越权替代 task contract

---

## 十二、下一步建议

最合理的下一步不是马上写很多 skill，而是继续补两份文档：

1. `docs/writer-skill-router.md`
内容：
- router 输入
- router 输出
- 评分规则
- 选 skill 上限
- fallback 机制

2. `docs/skills-first-batch.md`
内容：
- 第一批 6 个 skill 的 spec
- 每个 skill 的输入输出
- 正反例
- 与现有模块的接线点

等这两份定下来，再逐个把 skill 真正落成目录，会稳很多。
