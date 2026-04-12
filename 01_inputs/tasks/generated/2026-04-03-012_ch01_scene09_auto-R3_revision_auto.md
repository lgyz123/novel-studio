# task_id
2026-04-03-012_ch01_scene09_auto-R4

# goal
基于上一版草稿进行结构修复：写出《无住人间》第一章第九个短场景：孟浮灯在确认被监视后，决定采取更隐蔽的调查方式，利用收尸工作的日常性，在乱葬岗处理尸体时，尝试从尸体或环境中寻找与“阿绣”相关的细微线索，但遭遇新的阻力（如线索被清理、环境异常），从而将调查从主动观察转向被动发现，并引发一次微小的后果（如确认风险升级、线索中断）。本场重点：引发后果、提高风险、扩展世界信息。本次重点解决：根据该问题执行局部修补，避免不必要的整场重写。问题：正文提到'红绳和平安符'被拿走，但artifact_state显示红绳和平安符由孟浮灯持有，位置'贴身保留'或'随身携带'，visibility 'hidden'。正文写法与artifact_state不一致，违反task goal中'canon一致性风险'要求。；根据该问题执行局部修补，避免不必要的整场重写。问题：正文中使用了'麻绳'、'红绳'、'平安符'等motifs，但chapter_motif_tracker显示这些motifs的allow_next_scene为false或redundancy_risk为high，且avoid_motifs列表包含'麻绳'、'红绳'、'平安符'，违反约束。；根据该问题执行局部修补，避免不必要的整场重写。问题：Scene purpose要求风险等级从high升至critical，但正文中孟浮灯仅确认线索被清理，风险升级描述不够明确，可能未完全达到critical级别。

# based_on
02_working/drafts/ch01_scene09_v4.md

# scene_purpose
本场结束时，孟浮灯在乱葬岗处理尸体时，发现尸体或环境有异常（如新痕迹、物品缺失），确认调查线索被主动清理，风险从被监视升级为线索被阻断，迫使他调整调查策略。

# required_information_gain
- 乱葬岗环境的新变化（如土被翻动、物品位置移动）
- 尸体处理过程中的异常细节（如尸体状态、衣物痕迹）
- 孟浮灯对“阿绣”线索中断的认知

# required_plot_progress
孟浮灯在乱葬岗的日常劳动中，试图从尸体或环境寻找线索，但发现异常迹象（如土被翻动、物品缺失），确认对方已清理痕迹，线索中断，调查受阻。

# required_decision_shift
孟浮灯决定不再依赖主动观察，转为更被动的日常劳动中留意异常，调整调查策略以应对线索中断。

# required_state_change
- 风险等级从high升至critical
- 调查状态从主动观察转向被动发现
- 线索状态从可追踪变为中断

# avoid_motifs
- 麻绳
- 红绳
- 平安符
- 在码头
- 孟浮灯把绳
- 什么
- 着一把短刀
- 麻袋
- 他把绳

# chapter_state
03_locked/canon/ch01_state.md

# repair_mode
full_redraft

# repair_focus
structural_repair

# repair_plan
02_working/reviews/2026-04-03-012_ch01_scene09_auto-R3_repair_plan.json

# constraints
- 只允许孟浮灯作为核心视角人物；可引入环境作为背景，但不得新增角色
- 不引入谢观鱼、裴照骨、净苦和尚；不新增制度性设定；不急于抛出主线真相
- 重点写日常劳动动作、阻力体现（如线索被清理）、后果微现；文风克制
- 动作必须微小、隐蔽、可中断；不得让孟浮灯直接发现‘阿绣’相关明确证据
- 必须产生新的信息增量（如乱葬岗细节、异常发现）
- 必须出现主角新的现实动作或决策偏移（如改变调查策略）
- 本场必须服务于本章尚未完成的scene function（如引发后果、提高风险），不能继续过渡
- 确保时间线承接上一场，为白天或傍晚
- 结尾必须描述明确阻力后果（如确认线索中断、风险升级），风险等级从high升至critical
- 避免使用avoid_motifs中的元素，除非赋予新功能
- 本场必须产生新的信息增量，不能只重复上一场余波。
- 本场必须出现主角新的现实动作或决策偏移。
- 若复用上一场母题，必须赋予新的功能；否则改用不同触发物。
- 本场必须服务于本章尚未完成的 scene function，不能继续空转式过渡。
- structural_repair 允许动作：
- 允许补入一个关键动作、新事实、动作后果或结尾状态变化。
- 必须把 scene contract 缺失项补写落地，不能只做语言微修。
- structural_repair 允许动作：
- 允许补入一个关键动作、新事实、动作后果或结尾状态变化。
- 必须把 scene contract 缺失项补写落地，不能只做语言微修。
- structural_repair 允许动作：
- 允许补入一个关键动作、新事实、动作后果或结尾状态变化。
- 必须把 scene contract 缺失项补写落地，不能只做语言微修。
- 修订模式：full_redraft
- 修订焦点：structural_repair
- structural_repair 允许动作：
- 允许补入一个关键动作、新事实、动作后果或结尾状态变化。
- 必须把 scene contract 缺失项补写落地，不能只做语言微修。
- structural_repair 触发原因：
- reviewer 明确指出了结构缺口
- repair_plan 执行动作：
- 根据该问题执行局部修补，避免不必要的整场重写。问题：正文提到'红绳和平安符'被拿走，但artifact_state显示红绳和平安符由孟浮灯持有，位置'贴身保留'或'随身携带'，visibility 'hidden'。正文写法与artifact_state不一致，违反task goal中'canon一致性风险'要求。
- 根据该问题执行局部修补，避免不必要的整场重写。问题：正文中使用了'麻绳'、'红绳'、'平安符'等motifs，但chapter_motif_tracker显示这些motifs的allow_next_scene为false或redundancy_risk为high，且avoid_motifs列表包含'麻绳'、'红绳'、'平安符'，违反约束。
- 根据该问题执行局部修补，避免不必要的整场重写。问题：Scene purpose要求风险等级从high升至critical，但正文中孟浮灯仅确认线索被清理，风险升级描述不够明确，可能未完全达到critical级别。

# preferred_length
2000-3600字

# output_target
02_working/drafts/ch01_scene09_v5.md
