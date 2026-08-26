## ADDED Requirements

### Requirement: 普通正文不显示为思考
TUI MUST 仅把推理端独立发送的 `reasoning_content` 或 `reasoning` 字段显示为思考。普通 assistant
`content` MUST 显示为面向用户的助手正文，且系统提示不得要求模型把内部推演写入该正文。

#### Scenario: 无独立 reasoning 的普通对话
- **WHEN** 模型只发送普通 `content` 作为身份询问的回复
- **THEN** TUI 将其显示为助手正文，不显示为思考
