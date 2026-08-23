## MODIFIED Requirements

### Requirement: 上下文包含工具结果
`observe` 之后，下一次 `think` 调用 MUST 包含当前任务的原始用户指令、任务状态、最新有效观察，以及
满足 OpenAI tool 协议的近期完整工具调用链。系统 MUST NOT 因此重放同一会话已完成任务的用户／助手
消息或工具结果。当前任务的近期动作摘要达到固定上限时，系统 MUST 保留最近 6 条已完成动作；若保留
某条 tool 消息，MUST 同时保留对应的 assistant `tool_calls` 消息。

#### Scenario: 模型能看到当前任务工具输出
- **WHEN** 当前任务的 `screenshot` 返回文本摘要
- **THEN** 随后的 think 请求把该内容作为当前任务 tool 消息带上

#### Scenario: 下一任务不看到上一任务工具输出
- **WHEN** 一个任务完成后用户提交新指令
- **THEN** 新任务首个 think 请求不含上一任务的 tool 消息

#### Scenario: 保留调用与结果配对
- **WHEN** 当前任务已有已完成的工具调用且系统构造下一次 think 请求
- **THEN** 请求中的每条 tool 消息都有前序 assistant `tool_calls` 中匹配的 `tool_call_id`
