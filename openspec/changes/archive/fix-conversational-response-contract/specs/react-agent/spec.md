## ADDED Requirements

### Requirement: 用户可见正文与原生工具调用分离
GUI system MUST 要求模型把面向用户的答复写入普通 assistant 正文，并通过 OpenAI 兼容的 native
`tool_calls` 调用工具。system MUST NOT 要求正文输出 JSON、`thought`、`reason`、文本 `tool_calls` 或其它
内部协议字段。普通对话无需桌面操作时，模型 MUST 直接给出简洁答复；GUI 任务完成时，正文 MUST 给出
明确完成结论。

#### Scenario: 身份询问直接回答
- **WHEN** 用户询问 Agent 身份且不需要桌面操作
- **THEN** 助手正文包含直接身份答复，且不要求输出 `thought` 或 JSON 协议

#### Scenario: GUI 任务使用原生工具调用
- **WHEN** 用户要求执行桌面操作
- **THEN** 模型通过 native `tool_calls` 请求工具，普通正文不包含文本形式的工具调用对象
