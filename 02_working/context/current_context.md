# 写前诊断
来源文件：02_working/context/prewrite_review.md

第一步：铺陈世界观

【世界观构建】 已启动
确立核心法则…

- 我正在审视现有 manifest，确认力量体系、社会规则和天道逻辑是否已经闭环。
- 核心法则已有锚点：修行逻辑, 命、愿、债, 天道
- 生态位与社会应对已有锚点：王朝, 宗门, 司命机构
- 时空舞台已有锚点：运河, 城市, 山门
- 历史与变迁已有锚点：革命, 飞升

推演内在逻辑…

- 写作前需要先确认异常事物的生态位、制度反应和普通人的生存代价，否则场景容易只剩气氛没有后果。

勾勒时空轮廓…

- 我会优先检查主要舞台、历史变迁和当前剧情时点能否支持这一场 scene 的承接。

植入核心矛盾…

- 世界设定不仅要说明有什么，更要说明谁会因此受益、谁会因此受损、冲突如何落到人身上。

第二步：校准时间线

【时间线校验】 已启动
梳理长线骨架…

- 当前 book time：白天
- 近期事件：EVENT-001
- 近期事件：EVENT-002

# planner/bootstrap agent
来源文件：02_working/planning/bootstrap_state_machine.md

# 前置状态机

- planner/bootstrap agent：deterministic prewrite bootstrap
- task_id：2026-04-19-005_ch01_scene03_auto-RW8
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
产物：02_working/drafts/ch01_scene03_v3_rewrite8.md
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
- worldbu

[已截断]

# 世界观补全 proposal
来源文件：02_working/planning/worldview_patch.md

# 世界观补全 proposal

- planner/bootstrap agent：deterministic prewrite bootstrap
- task_id：2026-04-19-005_ch01_scene03_auto-RW8
- chapter_id：ch01
- 写入位置：02_working/planning/worldview_patch.md
- 说明：以下内容是写前补全候选，不直接进入 canon。

## 当前锚点
- 核心法则已有锚点：修行逻辑, 命、愿、债, 天道
- 生态位与社会应对已有锚点：王朝, 宗门, 司命机构
- 时空舞台已有锚点：运河, 城市, 山门
- 历史与变迁已有锚点：革命, 飞升

## 待补维度
- 当前没有显著缺口，可直接沿现有世界观写作。

## 建议补丁
- 本轮无需新增世界观补丁，建议保持 manifest 稳定。

## 与现有设定的衔接原则
- 新补丁必须回扣 `命、愿、债` 这类现有锚点，不要另起一套力量体系。
- 新补丁优先服务于场景可写性：能带来职业差异、风险后果、行动限制，而不是只增加名词。
- 在未人工确认前，这些内容只作为 02_working proposal 进入 writer context。

## 使用中的 skill：worldbuilding
来源文件：skills/worldbuilding/SKILL.md

# Worldbuilding

Use this skill to patch setting gaps in a way that directly improves scene writing.

## Use when

- The project needs worldbuilding completion proposals.
- Manifest materials are thematic but not yet operational.
- The task needs institutional response, spatial hierarchy, power-system limits, or region-specific survival logic.
- The user wants setting that affects b

[已截断]

# 时间线补全 proposal
来源文件：02_working/planning/timeline_patch.md

# 时间线补全 proposal

- planner/bootstrap agent：deterministic prewrite bootstrap
- task_id：2026-04-19-005_ch01_scene03_auto-RW8
- chapter_id：ch01
- 写入位置：02_working/planning/timeline_patch.md
- 说明：以下时间线只作为写前承接候选，不直接覆盖 story_state。

## 当前时间锚点
- current_book_time：白天
- recent_event：EVENT-001
- recent_event：EVENT-002

## 章节承接锚点
- 当前 chapter_state 里缺少明确的 scene 时序描述。

## 待补维度
- 当前时间线骨架可用。

## 建议时间线补丁

### 世界历史锚点
- 旧制成形：确立今天仍在运作的税役、差序和风险转嫁办法。
- 大灾或大战：解释为什么底层岗位被迫吸纳更多危险工作。
- 体制加码：说明当前制度为何更重登记、搜检、盘剥或隐性抽税。

### 本卷承接锚点
- 明确第一卷的起点时段、前三个关键局面变化、以及每次变化与上一场之间隔了多久。
- 如果 chapter_state 只写“夜里 / 次日 / 白天”，建议补一行相对顺序说明，避免 scene 承接漂移。

### 本章承接规则
- 每一场至少显式标明一个时间信号：夜里、次日清早、午后、傍晚、隔日等。
- 每次风险升级都要同步写明它发生在什么时段、和上一场相隔多久、为什么来得及或来不及处理。

## timeline skill router

- phase：timeline_bootstrap
- genre_tags：xianxia
- trope_tags：system
- demand_tags：planning、timeline、history

## selected_skills
- timeline-history｜mode=chapter-sequence｜score=0.93｜timeline_bootstrap 阶段需要把历史锚点与章节承接显式化。

## rejected_candidates
- worldbuilding｜mode=ins

[已截断]

# 角色补全 proposal
来源文件：02_working/planning/character_patch.md

# 角色补全 proposal

- planner/bootstrap agent：deterministic prewrite bootstrap
- task_id：2026-04-19-005_ch01_scene03_auto-RW8
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

[已截断]

# 章节工作大纲
来源文件：02_working/outlines/ch01_outline.md

# ch01_outline 工作稿

- planner/bootstrap agent：deterministic prewrite bootstrap
- task_id：2026-04-19-005_ch01_scene03_auto-RW8
- chapter_id：ch01
- 写入位置：02_working/outlines/ch01_outline.md
- 说明：这是 working outline，不直接替代 00_manifest 或 locked canon。

## 本章当前目标
- 基于上一版草稿进行结构修复：继续推进第1章，写出scene03。本章重点：从运河捞尸切入，建立底层视角与仙门录名黑幕。当前章节目标：从运河捞尸切入，建立底层视角与仙门录名黑幕的入口。本次重点解决：强化场景结构推进信号，明确状态变化；确保主角对青崖宗和录名候验的认知保持模糊；减少岸边等母题的冗余，同时保持叙事功能；增加一个只属于本章的新事实或压力来源；让主角基于误判采取行动，放大后续麻烦。

## 已有章节锚点
- 当前还缺少足够的章节锚点，建议用 locked scenes 或 chapter_state 补齐。

## 建议章节骨架
- 开场：先稳住主角当前求活状态与所处空间压力。
- 扰动：让一个低烈度异常或旧线索重新压到日常动作上。
- 试探：把线索从内部记挂推进到外部轻试探，但不要一次性升级成公开调查。
- 后果：让试探带来可验证的新阻力、风险、信息或关系变化。
- 章末偏移：主角形成新的处理方式，为下一章或下一场提供更明确的行为倾向。

## 近期正典事件提醒
- EVENT-001
- EVENT-002

## 与前置状态机的连接
- 角色创建阶段：把主视角、支撑角色、压力源角色的功能卡补齐。
- 大纲定制阶段：把上面的章节骨架改成当前项目真实的章内锚点与顺序。
- 第一章撰写阶段：基于本 outline 和 scene contract 继续落到具体 scene 任务。

## 使用中的 skill：scene-outline
来源文件：skills/scene-outline/SKILL.md

# Scene Outline

Use this skill to turn vague scene intent into a compact 

[已截断]





# 当前 scene contract
- 核心目标：基于上一版草稿进行结构修复：继续推进第1章，写出scene03。本章重点：从运河捞尸切入，建立底层视角与仙门录名黑幕。当前章节目标：从运河捞尸切入，建立底层视角与仙门录名黑幕的入口。本次重点解决：强化场景结构推进信号，明确状态变化；确保主角对青崖宗和录名候验的认知保持模糊；减少岸边等母题的冗余，同时保持叙事功能；增加一个只属于本章的新事实或压力来源；让主角基于误判采取行动，放大后续麻烦。

# 本次必须遵守的项目总纲
# 《无住人间》小说总纲

## 项目名称
《无住人间》

## 项目定位
- 长篇原创小说
- 修仙外壳下的现实主义群像
- 底层现实主义修仙 + 民间志怪 + 克味天道
- 非传统爽文

## 核心主题
- 底层人民
- 反对内卷
- 励志现实主义
- 禅意真理
- 写众生、见虚妄而不冷漠

## 不可动摇的核心需求
### 必须写到底层人民
底层人物不能只作为主角成长的背景板。每一卷都应有完整的普通人命运线，让读者记住他们的名字、选择与代价。

### 必须明确反对内卷
反的是把人变成可排名、可替换、可消耗资源的秩序，不是反努力，也不是鼓吹躺平。主角应当勤、韧，但拒绝把自我价值交给评价体系。

### 必须有励志感
励志不是一路赢，而是在看清世界恶意之后，仍愿意承担、学习、成长、保护别人。

### 必须有禅意真理
不直接灌输概念。真理要落实为角色抉择、因果反转与世界真相，做到“看破不说破太多，说破也要经由命运验证”。

### 必须保留感情重量
感情线必须与身份、制度、选择、代价绑定。爱不是休息区，而是暴露人物真实立场的镜子。

### 必须保持长篇潜力
设定不在开局一次性摊开；每一卷既要结算局部问题，也要打开更大层级。

## 长篇结构总纲
### 总体结构
- 六卷制
- 每卷独立矛盾 + 总线推进
- 主角路线：从捞尸少年到拆天梯之人
- 本质路线：以修仙写众生，以天道写制度，以真理写选择

### 分卷安排
#### 第一卷：灰灯卷
- 功能：从运河捞尸切入，建立底层视角与仙门录名黑幕
- 结尾状态：主角第一次得罪上层秩序

#### 第二卷：山门卷
- 功能：进入体制内部，看见精致化压榨与晋升神话
- 结尾状态：主角意识到朋友会被炼成材料

#### 第三卷：饥城卷
- 功能：把视角放到大饥荒和众生互害，考验互助可能
- 结尾状态：第一次建立民间活路网络又遭重创

#### 第四卷：京观卷
- 功能：庙堂、宗门、城市、军伍多线汇流，放大制度复杂度
- 结尾状态：女主开始动摇但仍未倒向主角

#### 第五卷：破相卷
- 功能：揭示天道与飞升真相，把“相

[已截断]

# 本次相关世界设定
# 《无住人间》世界观设定

## 世界观总述
本作不是要塑造一个完美仙界，而是写一个会吃人的世界里，人仍然彼此照亮的可能。世界气质为底层现实主义修仙、民间志怪与克味天道的结合，叙事重心落在“人间”而非“仙”。

## 社会结构
### 主要秩序维护者
- 王朝
- 宗门
- 司命机构
- 地方豪强
- 寺观

### 共同前提
这些力量彼此斗争，但共享同一个隐含前提：众生必须相信，只要继续竞争、继续服从、继续投入自我，就有可能更上一层。这个神话本身就是内卷机器。

### 制度表现形式
设定书明确要求通过以下事物展示制度如何运作：
- 门派考核
- 资源垄断
- 功绩排名
- 灵税体系
- 战功体系
- 户籍、符签、功牌、债册等登记与衡量机制

## 修行逻辑
### 修行资源的本质
这个世界的修行不只是吸灵气，而是围绕“命、愿、债”三条线展开。

### 三条主线
#### 命
寿数、劳作、血气。

#### 愿
执念、企盼、恨意、求生欲。

#### 债
每个人在制度中被登记、被衡量、被迫偿还的一切。

### 上层修行体系
上层会把“命、愿、债”加工成合法、精致、看起来天经地义的修行资源。

## 天道风格
### 基本性质
天道不是传统意义上的善恶裁判者，而更像一套宏大、冷漠、会吞没人的规则系统。

### 与修士的关系
越高阶的修士越接近“天”，也越容易失去人的完整性。所谓成仙，不应被写成单纯奖赏，而更像一种异化。

### 真理与虚妄的表达
作品用“相”来代表名分、境界、荣誉、正邪标签，并逐步揭示其虚妄性。

## 克味限制
可以有异相、认知扭曲、法相畸变、天道不

[已截断]

# 本次相关人物设定
### 孟浮灯
- 身份：男主，运河收尸学徒
- 核心矛盾：既要活下去，又不愿看人被抹成无名之物
- 人物方向：从捞尸少年走向拆天梯之人
- 写法要求：不能写成天降主角光环，要从经验与选择中长出来

# 人工输入总表
# Human Input
- 说明：以下内容属于人工明确指定的项目输入，自动流程默认优先服从这一层。

## 项目信息
- 小说名：无住人间
- 类型：底层现实主义修仙
- 受众：喜欢长篇中文网文、群像、现实主义修仙的读者
- 风格：克制、冷静、以细节和动作落地
- 语气：人间苦烈，但保留照亮彼此的余温
- 一句话卖点：从运河捞尸少年写起，沿着众生命运一路拆到天梯尽头
- 故事梗概：孟浮灯在运河与码头底层求活时，被一具来历异常的尸体和它牵出的名字卷入更大的秩序黑幕。
- 主题：反内卷、写众生、见虚妄而不冷漠

## 主角
- 姓名：孟浮灯
- 定位：底层捞尸少年
- 背景：长期在运河、码头和乱葬岗一线做脏活，熟悉底层求活规矩。
- 描述：警惕、耐压、克制，不轻易把疑问外露。
- 当前目标：先在不暴露自己的前提下活下去，再判断是否要追索异常线索。
- 核心欲望：想保住自己和身边少数还能互相照应的人。
- 核心恐惧：被更高层秩序盯上，连求活余地都被夺走。

## 次要角色
- 老张头｜同行老人｜底层行当里的前辈｜能提供现实阻力、行业经验和微弱的人情承接。

## 世界与约束
- 时代：古代中国风异世
- 主要舞台：运河、码头、乱葬岗、窝棚、货栈、寺观与下层城市边缘
- 力量体系：围绕命、愿、债运转的修行与登记体系
- 社会秩序：王朝、宗门、司命机构、地方豪强、寺观共同维持吃人的秩序
- 禁区：不要把修行写回单纯吸灵气升级；不要把天道写成简单善恶裁判。

## 故事蓝图
- 开场局面：第一章已完成从运河捞尸切入、线索初现与风险抬头；第二章需要把局面从单场异动推成更稳定的章内压力。
- 核心冲突：底层求活逻辑与上层秩序黑幕逐步碰撞，主角每多知道一点，就更容易失去退路。
- 当前章节目标：第二章先确立新的日常压力源，再让主角被迫形成更明确的应对方式。
- 首章目标：从运河捞尸切入，建立底层视角与仙门录名黑幕的入口。

## 必须打到的拍点
- 新章开场必须出现新的现实问题，不只是延续上一章余波。
- 主角要做出一次带后果的微决策。

## 当前避免的拍点
- 不要一上来就把更高层真相全部掀开。
- 不要跳成大场面冲突或爽文式反击。

## 必须出现
- 每场都要有可验证的新信息、新动作或现实后果中的至少两项。
- 底层日常必须是剧情推进载体，不只是背景板。

## 必须避免
- 不要现代词汇、现代设施、现代口语。
- 不要后宫、脸谱反派、流水线升级。

## 当前待定
- 第二章的核心压力源具体落在哪条线最合适：人、物、规矩还是搜查后果？

## 人工验收清单
- 结尾是否真的改变了下一场的处理方式？
- 是否把世界设定落在了物件、动作和风险上，而不是解释段上？

## 人工指定参考文件
- 00_manifest/novel_manifest.md
- 00_manifest/world_bible.md
- 00_manifest/character_bible.md


# 本次生活素材使用规则
- 生活素材只能提取气氛、感官、情绪、节奏、意象
- 禁止直接搬运现代现实世界的具体物件或设施进入小说场景
- 如与小说世界冲突，必须优先服从小说设定

# 本次可借用的生活素材
今天下班的时候，天已经黑了。便利店门口有人蹲着抽烟，风很冷，路边停着几辆沾了灰的车。我突然觉得城市并不是不说话，它只是一直在低声重复同一种疲惫。

# 当前章节状态
来源文件：03_locked/canon/ch01_state.md

# ch01 当前状态

## 本章定位
- 所属卷：灰灯卷
- 本章功能：从运河捞尸切入，建立底层视角与仙门录名黑幕
- 直接前文：00_manifest/novel_manifest.md

## 本章主线骨架
- 本章目标：从运河捞尸切入，建立底层视角与仙门录名黑幕的入口。
- 新压力源：把局面从单场异动推成更稳定的章内压力
- 错误判断：主角先把异常余波当成做活路上的附带麻烦，误以为还能靠老办法压过去。
- 不可逆后果：主角会因为一次求稳处理留下回不了头的后果，旧的求活顺序被迫改写。
- 结尾状态：先在不暴露自己的前提下活下去，再判断是否要追索异常线索。 同时避免：不要一上来就把更高层真相全部掀开。

## 已锁定场景
- [待生成本章锁定场景]

## 当前主角状态
- 主角：孟浮灯
- 当前默认目标：先在不暴露自己的前提下活下去，再判断是否要追索异常线索。

## 已锁定线索
- [待从前文与 story_state 回填]

## 暂不展开的内容
- 第二章的核心压力源具体落在哪条线最合适：人、物、规矩还是搜查后果？
- 不要现代词汇、现代设施、现代口语。
- 不要后宫、脸谱反派、流水线升级。

## scene01 建议目标
- 写出 ch01 的开场承接，让局面在上一章基础上出现新的可验证变化。
- 第一场既要重新落地人物生存处境，也要给出本章独有的新压力、新线索或新后果。
- 本场优先服务：把局面从单场异动推成更稳定的章内压力


# 最近结构化场景摘要
- ch01_scene01｜发现线索
  - 新信息：拖到一半，他停住了。不是累，是看见了东西。；尸体的右手攥着，指节僵得掰不开，但掌心里露出一角纸，被水浸透了，糊成一团…
  - 新动作/决策：拖到一半，他停住了。不是累，是看见了东西。
  - 状态变化：protagonist_mode: 观察/求活 -> 隐匿/压制；investigation_stage: 未启动 -> 被动留意
  - 物件变化：麻绳；录名册
- ch01_scene02｜发现线索
  - 新信息：不是码头苦力常穿的粗麻，也不是城里小吏那种规整的补子。布料本身不算顶好，…；平常的法子是拖到义庄后头那片空地，等管事的来验看、登记，然后要么等人认领…
  - 新动作/决策：孟浮灯把尸体拖到岸边，没急着翻检。他先蹲下来，把麻绳从尸身腋下抽出来，一圈圈绕回自己腰间。水顺着…
  - 状态变化：risk_level: low -> high
  - 物件变化：水顺着绳；那些挂着牌

# 相关 tracker 摘要
- 章节目标：维持日常求活与从运河做活
- 主角当前目标：[待从前文与 story_state 回填]；拖到一半，他停住了。不是累，是看见了东西
- 当前模式 / 调查阶段 / 风险：隐匿/压制 / 被动留意 / high
- 当前未解问题：第二章的核心压力源具体落在哪条线最合适：人、物、规矩还是搜查后果？；不要现代词汇、现代设施、现代口语；不要后宫、脸谱反派、流水线升级
- 已确认事实：[待从前文与 story_state 回填]；拖到一半，他停住了。不是累，是看见了东西；尸体的右手攥着，指节僵得掰不开，但掌心里露出一角纸，被水浸透了，糊成一团…
- 待验证事实：他认得这身灰布短打，是西岸苦力营的样式，但脸泡得发胀，辨不出是谁；下面是一列列名字，大多糊了，唯独中间一个名字，墨迹格外深，像是后来添上去的，水也没能完全化开；可当他走回草棚时，却发现席子被掀开了一角——不是风吹的，那痕迹太整齐，像是有人翻检过
- 关键物件切片：麻绳（持有者：主角；位置：随身携带；可见性：hidden）；录名册（持有者：主角；位置：随身携带；可见性：hidden）；说要攒钱（持有者：主角；位置：随身携带；可见性：hidden）
- 章节结构锚点：首个线索场=ch01_scene01；首个旧识暗示场=ch01_scene01；首个调查触发场=ch01_scene01

# scene writing skill router
来源文件：02_working/planning/scene_writing_skill_router.md


- phase：scene_writing
- genre_tags：xianxia
- trope_tags：system
- demand_tags：continuity、scene-writing

## selected_skills
- continuity-guard｜mode=scene-canon｜score=0.95｜scene 写作依赖 chapter_state、story_state 或 tracker 承接，默认必须启用 continuity-guard。

## rejected_candidates
- worldbuilding｜mode=institutional｜score=0.2｜当前是正文落稿阶段，世界观补丁已应在 planning 阶段提前生成。

## risk_flags
- 无


# writer skill：continuity-guard
来源文件：skills/continuity-guard/SKILL.md

# Continuity Guard

Use this skill to keep a scene inside the project's established state instead of letting prose drift override canon.

## Use when

- The task depends on `chapter_state`, `story_state`, or tracker slices.
- The scene is a continuation, `revise`, or `rewrite` task.
- The draft must preserve artifact locations, risk levels, relationship status, or investigation stage.
- The user asks for stronger continuity or canon consistency.

## Do not use when

- The task is pure brainstorming with no canon constraints.
- The task is only naming or only worldbuilding.

## Required inputs

Read only the files you need:

- `01_inputs/tasks/current_task.md`
- `03_locked/canon/chXX_state.md` when present in the task
- `03_locked/state/story_state.json`
- relevant tracker files under `03_l

[已截断]

参考：skills/continuity-guard/references/checklist.md

# Continuity Checklist

Use this checklist to derive the smallest possible set of writer guardrails.

## State

- Current book time
- Relative order vs previous scene
- Protagonist mode
- Investigation stage
- Risk level

## Artifacts

- Holder
- Location
- Visibility
- Whether the item changed in recent scenes

## Rel

[已截断]

参考：skills/continuity-guard/references/conflicts.md

# Common Continuity Conflicts

## Artifact reset

Pattern:

- tracker says an item is carried on body
- draft writes it as hidden in a box, shelf, or room again

Response:

- preserve tracker state
- rewrite the scene action around the current artifact position

## Time blur

Pattern:

- chapter state says `次日` or `白天`

[已截断]

# skill audit
来源文件：02_working/planning/skill_audit.md

# skill audit

## planning_bootstrap
- selected_skills：worldbuilding、scene-outline
- major_issues：无
- minor_issues：
  - planning_bootstrap router 当前启用：worldbuilding、scene-outline。
- is_ok：True

## character_creation
- selected_skills：character-design、naming
- major_issues：无
- minor_issues：
  - character_creation router 当前启用：character-design、naming。
- is_ok：True

## timeline_bootstrap
- selected_skills：timeline-history
- major_issues：无
- minor_issues：
  - timeline_bootstrap router 当前启用：timeline-history。
- is_ok：True

## scene_writing
- selected_skills：continuity-guard
- major_issues：无
- minor_issues：
  - scene_writing router 当前启用：continuity-guard。
- is_ok：True

# 少量必要 prose 参考
来源文件：02_working/drafts/ch01_scene03_v3_rewrite7.md
- 仅用于承接声口与场面，不得顺着旧文风滑行，更不能照抄旧场气氛。

但他没意识到，这个看似稳妥的拖延，恰恰留下了最要命的痕迹——席子下的尸体还在原地，而夜晚的运河边，并不只有他一个人会来。
