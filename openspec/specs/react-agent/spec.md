# react-agent Specification

## Purpose

LangGraph ReAct 循环、状态、JSON 检查点、中断恢复。
## Requirements
### Requirement: 系统契约引导复用当前帧定位

每次 `think` 的 GUI 系统契约 MUST 要求模型先取得并阅读最新截图，再使用该截图中的视图像素调用 `mouse_move`。契约 MUST NOT 要求或推荐已禁用的定位工具、`target_id` 或定位编号；需要确认控件文字时 MUST 指导模型调用 `ocr`。移动后模型 MUST 依据后置截图的光标核验决定是否调用无坐标的 `mouse_click`。

#### Scenario: 只用视图像素移动

- **WHEN** 当前任务需要点击图标或按钮
- **THEN** system 提示模型使用当前截图视图像素调用 `mouse_move`，且不要求先调用 `locate`

#### Scenario: 需要读字时使用 OCR

- **WHEN** 截图中的控件文字无法直接读清
- **THEN** system 提示模型调用 `ocr` 获取文字，不调用 `locate`

### Requirement: ReAct 状态机
Agent SHALL 用 LangGraph StateGraph 实现 `think`、`act`、`observe` 节点。一个回合 MUST 从 `think` 开始。若模型返回工具调用，图 MUST 先跑 `act` 再 `observe`。普通工具观察后 MUST 回到 `think`；仅当独立完成证据校验通过后才 MUST 从 `observe` 结束。纯对话或只读观察任务中，模型不再返回工具调用时图 MUST 以 `done` 结束。任务已经成功执行副作用但尚未通过完成声明与独立校验时，模型不返回工具调用 MUST NOT 直接结束；图 MUST 保留正文、标记仍需完成验证并再次进入 `think`，且该重试计入迭代上限。恢复护栏耗尽时图 MUST 以 `error` 结束。

#### Scenario: 纯文本完成
- **WHEN** 模型返回最终助手消息且当前任务未执行副作用
- **THEN** 图状态为 `done`，且不调用任何工具

#### Scenario: 一次工具循环
- **WHEN** 模型返回普通工具调用且工具成功
- **THEN** 图执行 `act` 再 `observe`，追加工具结果，并再次调用 `think`

#### Scenario: 副作用后正文不能直接完成
- **WHEN** 最近成功副作用已经回注截图，但模型只返回正文且没有调用完成声明工具
- **THEN** 图不标记 `done`，任务胶囊提示仍需完成验证并再次调用 `think`

#### Scenario: 完成声明通过后结束
- **WHEN** 模型在成功副作用的后置截图之后调用 `task_complete` 且参数有效，并且声明后的独立观察校验通过
- **THEN** 图经过 `act`、声明后观察与校验后以 `done` 结束，不再额外调用模型

#### Scenario: 完成校验失败继续
- **WHEN** `task_complete` 的独立后置观察或证据校验失败
- **THEN** 图不得以 `done` 结束，而是向模型回注失败原因并回到 `think`

### Requirement: 迭代上限

Agent MUST 在单次用户回合中，于配置的最大 Think/Act/Observe 循环次数后停止。触达上限时，状态 MUST 为 `error`，记录 MUST 包含迭代上限说明。未设置 `MAX_GUI_MAX_ITERATIONS` 时，`max_iterations` MUST 默认为 20。

#### Scenario: 达到最大迭代

- **WHEN** 模型在 `max_iterations` 轮之后仍继续请求工具
- **THEN** Agent 不再分发下一个工具，并向用户报告已达迭代上限

#### Scenario: 未配置环境变量

- **WHEN** 进程未设置 `MAX_GUI_MAX_ITERATIONS`
- **THEN** 配置中的最大循环次数为 20

### Requirement: 中断与恢复

Agent MUST 接受来自 TUI 的中断。中断状态 MUST 写入该会话 JSON 中的检查点。恢复同一会话 MUST 从最近检查点恢复图状态，而不是从头重跑该回合，除非用户开始新回合。不得使用 SQLite 保存检查点。

#### Scenario: 运行中中断

- **WHEN** 用户在 `think` 或 `act` 期间中断
- **THEN** 状态变为 `interrupted`，检查点写入该会话 JSON

#### Scenario: 中断后恢复

- **WHEN** 用户在中断后继续同一会话
- **THEN** Agent 加载最近检查点并从该节点继续

### Requirement: 上下文包含工具结果

`observe` 之后，下一次 `think` 调用 MUST 包含此前的用户/助手消息以及本回合最新工具结果。

#### Scenario: 模型能看到工具输出

- **WHEN** `screenshot` 返回文本摘要
- **THEN** 随后的 `think` 模型请求把这些内容作为 tool 消息带上

### Requirement: GUI 系统契约注入

每次 `think` 发给模型的消息列表 MUST 以一条中文 `role=system` 消息开头。该消息 MUST 要求：桌面任务一律用键鼠完成；每一次键鼠动作都必须截图核验；还没有画面时先 `screenshot`；要点、拖、输入前先 `mouse_move`，根据回注图上的光标判断位置，对了再调用不带坐标的 `mouse_click` 或拖拽/键盘；看到回注图后 MUST 先判断红十字落在哪个控件上，与目标不一致则再 `mouse_move`，MUST NOT 在未看图时点击；坐标只用最近一帧视图像素，且视图像素必须落在该帧 `view_width`×`view_height` 内；不要用逻辑分辨率、屏幕百分比或归一化坐标，也不要把工具摘要里的逻辑坐标再当输入；看不清字再调用 `ocr`；MUST NOT 调用或尝试调用 `locate`；破坏性桌面动作一次一个；动作后根据新画面判断是否进入下一子任务；首轮尽量输出编号子任务。该消息 MUST 写明当前操作系统的中文名称；当主机为 macOS 时 MUST 写明不是 Windows，快捷键用 `command` 而不是 `windows`。若当前会话已有视图帧，该消息 MUST 包含该帧的 `view_width` 与 `view_height`。该 `system` 消息 MUST NOT 写入会话 JSON，MUST NOT 作为 TUI 记录区条目出现。

#### Scenario: think 请求带 system

- **WHEN** Agent 进入 `think` 并调用推理客户端
- **THEN** 请求的 `messages` 第一条 `role` 为 `system`，正文含「先截图」、视图像素约定与视图宽高边界，且不含 `target_id` 或定位编号

#### Scenario: 会话不保存 system

- **WHEN** 一回合结束并落盘
- **THEN** 该会话 JSON 的 `messages` 中没有 `role` 为 `system` 的条目

### Requirement: think 推理异常结束为 error

`think` 调用推理客户端失败时，客户端 MUST 先按推理重试策略处理可重试错误。每次网络重试 MUST 保持在同一次 `think` 和同一 ReAct iteration 内，MUST NOT 重新执行已经成功的工具。仅当错误不可重试、流已产生有效增量后失败、用户中断或重试耗尽时，控制权才返回 Agent。最终推理失败时 Agent MUST 将图状态设为 `error`，写入人类可读错误，MUST NOT 把未捕获异常甩出图外导致会话仍为上一回合的 `done`；用户中断仍按既有中断语义处理。

#### Scenario: 瞬时错误重试成功

- **WHEN** `/chat/completions` 首次发生可重试错误且后续尝试成功
- **THEN** `AgentRunner` 继续当前 `think`，图 iteration 不增加，且只提交一条成功的助手消息

#### Scenario: 重试不得重复桌面动作

- **WHEN** 前一轮已经成功执行桌面工具，下一轮 `think` 在首个流式增量前重试
- **THEN** Agent 不重新进入前一轮 `act`，也不重复执行该桌面工具

#### Scenario: 流式 HTTP 错误变成会话错误

- **WHEN** `/chat/completions` 返回不可重试非 2xx，或可重试错误达到最大重试次数
- **THEN** `AgentRunner.run` 返回的状态 `status` 为 `error`，且该状态被写入当前会话

### Requirement: 轻量计划状态

`AgentState` MUST 包含 `plan`（字符串列表）与 `current_subtask`（当前子任务文本或空）。旧检查点缺少这两项时 MUST 视为空计划并仍能恢复。图拓扑 MUST 仍为 `think` / `act` / `observe`，不得增加独立 plan 节点。

当助手文本含至少两行「数字 + `.` 或 `)` + 内容」的编号列表时，Agent MUST 用该列表覆盖 `plan`，并将 `current_subtask` 设为第一项。助手文本含「改计划」且带新编号列表时 MUST 同样覆盖并重置到第一项。工具失败时 MUST NOT 改动当前子任务。助手文本含「子任务完成」或「下一子任务」且 `plan` 非空时，Agent MUST 将当前项推进到下一项（已在末项则保持）。解析失败 MUST NOT 中断 ReAct 循环。

#### Scenario: 首轮编号列表写入计划

- **WHEN** 模型返回含「1. 打开计算器」与「2. 输入 1+1」的助手文本
- **THEN** 状态 `plan` 含这两项，`current_subtask` 为「打开计算器」

#### Scenario: 工具失败不推进子任务

- **WHEN** 当前子任务为计划第一项且本次工具调用失败
- **THEN** `current_subtask` 仍为第一项

#### Scenario: 旧检查点缺计划字段

- **WHEN** 中断检查点没有 `plan` 或 `current_subtask`
- **THEN** Agent 仍能从该检查点恢复，计划视为空

### Requirement: 图执行期间发出进度

`AgentRunner` 在每个节点进入时 MUST 回调当前状态名（`thinking` / `acting` / `observing`）。流式思考与正文 MUST 在 `think` 等待模型期间分别回调。一条助手消息在 `think` 拼装完成后 MUST 立即回调 `on_message`。`act` 中每完成一次 `registry.invoke` MUST 立即回调该条 tool 消息，MUST NOT 等到本节点全部工具结束。

#### Scenario: 状态随节点变化

- **WHEN** 模型返回工具调用并进入 `act`
- **THEN** 在工具执行前调用方已收到状态 `acting`

#### Scenario: 单次工具完成后即可见

- **WHEN** 一次 `think` 请求了两个工具且 `act` 顺序执行
- **THEN** 第一个工具返回后，调用方在第二个工具返回前已收到该 tool 的 `on_message`

### Requirement: think 与 act 增量持久化

`think` 产生助手消息后 MUST 立刻写入当前会话 JSON。`act` 每完成一个工具 MUST 立刻将该 tool 消息写入当前会话 JSON。图正常结束时 MUST 更新 `status` 与检查点，MUST NOT 把已写入的同一条消息再追加一次。

#### Scenario: 工具循环中途会话已有助手消息

- **WHEN** 模型返回带工具调用的助手消息且 `act` 尚未全部完成
- **THEN** 该会话 JSON 已包含这条助手消息

#### Scenario: 结束不重复追加

- **WHEN** 一回合含一次工具循环后以无工具调用结束
- **THEN** 会话 JSON 中该助手与 tool 消息各出现一次

### Requirement: Agent 在关键边界发出运行事件

`AgentRunner` MUST 在运行开始、恢复、终止、状态迁移、模型调用开始/结束/失败、工具调用开始/结束/失败和观察完成时发出结构化运行事件。`tool.started` MUST 在调用 `registry.invoke` 前发出；工具结束事件 MUST 在对应 tool 消息提交会话后发出并引用其消息下标。系统 MUST NOT 为每个正文或 reasoning token 持久化独立运行事件。

#### Scenario: 工具调用前先产生开始事件

- **WHEN** 模型请求一个工具且 Agent 即将调用 `registry.invoke`
- **THEN** `tool.started` 的顺序号小于对应 `tool.completed` 或 `tool.failed`

#### Scenario: 模型完成事件引用已提交消息

- **WHEN** 一次 think 完成并把助手消息写入会话
- **THEN** 随后的 `model.completed` 含该助手消息的 `session_message_index`

#### Scenario: token 流不膨胀运行日志

- **WHEN** 一次模型响应流式产生多个正文与 reasoning token
- **THEN** TUI 仍按 token 更新，但运行日志只在该模型调用边界记录汇总事件

### Requirement: 模型完成事件携带 token 用量

当一次 `think` 的模型调用成功结束时，`model.completed` 的 `data` MUST 在用量已知时包含非负整数 `prompt_tokens`、`completion_tokens` 与 `total_tokens`。用量未知时 MUST NOT 把这三项写成 0，MUST 省略或使用 `null`。该事件 MUST 继续只记录诊断字段，MUST NOT 复制正文或 reasoning 原文。`model.failed` 仅在失败前已解析到 `usage` 时写入同样字段。

#### Scenario: 成功调用写入用量

- **WHEN** 推理客户端返回带 `prompt_tokens=12`、`completion_tokens=8`、`total_tokens=20` 的完整回复，且助手消息已写入会话
- **THEN** 随后的 `model.completed` 含这三项用量，且不含回复原文

#### Scenario: 未知用量不记零

- **WHEN** 推理客户端完成流式回复但用量未知
- **THEN** `model.completed` 不含 0 值的 `prompt_tokens` / `completion_tokens` / `total_tokens`，或这三项为 `null`

### Requirement: Agent 终态与运行终态一致

当 Agent 状态变为 `done`、`error` 或 `interrupted` 时，系统 MUST 分别发出 `run.completed`、`run.failed` 或 `run.interrupted`。推理异常事件 MUST 记录异常类型和经过清理的可读摘要，MUST NOT 记录请求密钥或 Authorization Header。

#### Scenario: 推理异常形成失败时间线

- **WHEN** `think` 中推理客户端抛出异常并把 Agent 状态设为 `error`
- **THEN** 运行事件依次包含 `model.failed` 和 `run.failed`，会话 checkpoint 终态仍为 `error`

### Requirement: 未闭合桌面动作不得自动重放

如果恢复时运行日志存在桌面副作用工具的 `tool.started` 而没有对应结束事件，系统 MUST 把该调用视为结果未知并记录诊断，MUST NOT 因运行日志状态自动重新调用该工具。后续 Agent 行为仍由恢复后的重新观察和模型决策决定。

#### Scenario: 点击后进程异常退出

- **WHEN** `mouse_click` 已产生 `tool.started` 但进程在结束事件前退出，随后用户恢复任务
- **THEN** 系统报告上次动作结果未知，且不直接重放该次点击

### Requirement: Agent 按阶段暴露并分发工具

每次 `think` MUST 根据当前活动截图和任务完成门状态选择工具 schema。无活动截图时 MUST 暴露初始观察工具，MUST NOT 暴露桌面副作用工具；有活动截图时 MAY 暴露定位和桌面动作；只有任务已成功执行副作用并取得后置截图时才 MUST 暴露 `task_complete`。`act` MUST 再次检查调用名称属于产生该回复时的允许集合，MUST NOT 只依赖提示词或 schema 隐藏。

#### Scenario: 无截图只开放观察

- **WHEN** 新桌面任务尚无活动 `ViewFrame`
- **THEN** 请求包含 `screenshot` 等初始观察 schema，不包含 `mouse_click`、`keyboard_type` 或 `task_complete`

#### Scenario: 有截图开放桌面动作

- **WHEN** 当前任务已有活动 `ViewFrame`
- **THEN** 请求可包含定位、移动、点击与键盘工具 schema

#### Scenario: 幻觉调用不能绕过阶段

- **WHEN** 模型返回当前阶段未暴露的副作用工具名
- **THEN** `act` 返回稳定的阶段拒绝错误且不执行工具实现

### Requirement: 同一观察最多执行一个副作用工具

每次 `think` 返回的调用批次 MUST 按原顺序处理。系统 MAY 执行第一个副作用之前的只读调用和第一个副作用；第一个副作用之后的所有调用 MUST 返回 `action_batch_blocked`，MUST NOT 调用其实现。所有原始 `tool_call_id` MUST 取得一条配对 tool 消息。`mouse_move` MUST 视为副作用。

#### Scenario: 两个副作用只执行第一个

- **WHEN** 同一模型回复依次调用 `mouse_move` 与 `mouse_click`
- **THEN** 系统执行 `mouse_move`，拒绝 `mouse_click`，两次调用都有配对 tool 消息，并在下一次动作前先进入观察

### Requirement: 批次阻断进入恢复护栏

一次 `observe` 中只要存在 `action_batch_blocked`，系统 MUST 按该批次记录一次稳定的恢复失败，并向下一次
`think` 回注“只提交一个副作用、先观察后置截图”的恢复提示；同一批次内任意数量的被阻断调用 MUST NOT
多次增加恢复计数。相同批次违规在同一活动截图上连续达到既有恢复阈值时，Agent MUST 以
`recovery_exhausted` 结束。成功 `screenshot` MUST 清除该恢复状态。

#### Scenario: 单批次多个阻断调用只计一次

- **WHEN** 一个模型回复的首个副作用后还有多个调用，且它们都返回 `action_batch_blocked`
- **THEN** 本次观察仅将恢复失败计数增加一次

#### Scenario: 重复批次有界终止

- **WHEN** 模型在同一活动截图上连续两次回复包含多个副作用调用
- **THEN** 第二次观察后 Agent 状态为 `error`，错误与终止原因为 `recovery_exhausted`

#### Scenario: 重新截图解除护栏

- **WHEN** 批次阻断后模型先成功调用 `screenshot`
- **THEN** 恢复失败计数清零，下一次可按单个副作用协议继续执行

#### Scenario: 只读后执行一个副作用

- **WHEN** 同一模型回复先调用 `screen_info` 再调用 `mouse_move`
- **THEN** 系统按顺序执行两者，并在 `mouse_move` 后停止处理后续调用

### Requirement: 副作用任务使用完成声明门

系统 MUST 提供非副作用控制工具 `task_complete`，要求非空的中文完成摘要与可见证据。任务成功执行任一副作用并取得后置截图后，任务胶囊 MUST 持久化 `completion_required=true`。`task_complete` 只有在最近成功副作用带后置截图且参数有效时才能令 `completion_verified=true`；旧 checkpoint 缺少这些字段时 MUST 安全视为未要求、未通过。

#### Scenario: 没有后置截图拒绝完成

- **WHEN** 最近副作用没有成功取得后置截图，模型调用 `task_complete`
- **THEN** 系统返回完成验证失败，任务不进入 `done`

#### Scenario: 完成门状态可恢复

- **WHEN** 会话在成功副作用后中断并恢复
- **THEN** 恢复后的任务仍要求 `task_complete`，不会因恢复丢失完成门

### Requirement: ReAct 观察选择单一主 UI 通道

每个 `observe` MUST 先获得前台身份和截图，再按以下顺序选择一个主 UI 上下文：存在原生模态对话框时选择 `native`；否则受控浏览器页面可用时选择 `browser`；否则选择 `vision`。系统 MUST 将选中的有限 UI 快照、版本和状态摘要注入下一次 `think`，MUST NOT 同时把完整 browser 与 native 元素集合交给模型。

#### Scenario: 受控网页无原生弹窗
- **WHEN** Chrome 为前台、Playwright 页面可用且没有原生模态对话框
- **THEN** 下一次 `think` 得到 browser UI 快照摘要

#### Scenario: 原生弹窗覆盖网页上下文
- **WHEN** Chrome 前台但观察到文件选择器
- **THEN** 下一次 `think` 得到 native UI 快照摘要而非网页元素列表

### Requirement: 通道动作触发统一后置观察

BrowserBackend、MacOSAXBackend 和视觉后备的每一个成功副作用 MUST 经 `observe` 创建新观察、更新或作废 UI 快照，并用既有 expectation／progress 机制判断动作效果。通道不可用或动作失败 MUST 向下一次 `think` 提供不含敏感定位信息的恢复诊断。

#### Scenario: AXPress 后快照刷新
- **WHEN** AXPress 成功执行
- **THEN** Agent 进入 `observe`，旧 AX 元素失效并依据新观察验证动作预期
