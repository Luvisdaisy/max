## MODIFIED Requirements

### Requirement: 上下文包含工具结果

`observe` 之后，下一次 `think` 调用 MUST 包含此前的用户/助手消息以及本回合最新工具结果。

#### Scenario: 模型能看到工具输出

- **WHEN** `screenshot` 返回文本摘要
- **THEN** 随后的 `think` 模型请求把这些内容作为 tool 消息带上
