## ADDED Requirements

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
