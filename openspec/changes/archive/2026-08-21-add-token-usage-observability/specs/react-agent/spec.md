## ADDED Requirements

### Requirement: 模型完成事件携带 token 用量

当一次 `think` 的模型调用成功结束时，`model.completed` 的 `data` MUST 在用量已知时包含非负整数 `prompt_tokens`、`completion_tokens` 与 `total_tokens`。用量未知时 MUST NOT 把这三项写成 0，MUST 省略或使用 `null`。该事件 MUST 继续只记录诊断字段，MUST NOT 复制正文或 reasoning 原文。`model.failed` 仅在失败前已解析到 `usage` 时写入同样字段。

#### Scenario: 成功调用写入用量

- **WHEN** 推理客户端返回带 `prompt_tokens=12`、`completion_tokens=8`、`total_tokens=20` 的完整回复，且助手消息已写入会话
- **THEN** 随后的 `model.completed` 含这三项用量，且不含回复原文

#### Scenario: 未知用量不记零

- **WHEN** 推理客户端完成流式回复但用量未知
- **THEN** `model.completed` 不含 0 值的 `prompt_tokens` / `completion_tokens` / `total_tokens`，或这三项为 `null`
