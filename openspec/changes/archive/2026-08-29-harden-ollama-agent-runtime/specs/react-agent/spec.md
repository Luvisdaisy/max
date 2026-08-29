## MODIFIED Requirements

### Requirement: ReAct 状态机

Agent SHALL 用 LangGraph StateGraph 实现 `think`、`act`、`observe` 节点。一个回合 MUST 从 `think` 开始。若模型返回工具调用，图 MUST 先跑 `act` 再 `observe`。普通工具观察后 MUST 回到 `think`；完成声明通过后 MUST 从 `observe` 结束。纯对话或只读观察任务中，模型不再返回工具调用时图 MUST 以 `done` 结束。任务已经成功执行副作用但尚未通过完成声明时，模型不返回工具调用 MUST NOT 直接结束；图 MUST 保留正文、标记仍需完成验证并再次进入 `think`，且该重试计入迭代上限。

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

- **WHEN** 模型在成功副作用的后置截图之后调用 `task_complete` 且参数有效
- **THEN** 图经过 `act` 与 `observe` 后以 `done` 结束，不再额外调用模型

## ADDED Requirements

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
