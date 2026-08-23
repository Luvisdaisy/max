## ADDED Requirements

### Requirement: 监控面板展示 token 用量

独立运行监控面板 MUST 展示本次运行已累计的输入、输出与合计 token。有已知累计时 MUST 使用中文「用量：输入 N / 输出 M / 合计 T」形式。没有任何已知用量时 MUST 显示「用量：未知」，MUST NOT 显示输入 0、输出 0 来表示未知。最近事件中的模型完成摘要 MUST 包含当次输入与输出，或在当次未知时写「用量未知」。用量 MUST NOT 作为用户、助手或工具消息写入会话记录区。

#### Scenario: 模型完成后面板出现累计用量

- **WHEN** Agent 发出带 `prompt_tokens=12`、`completion_tokens=8`、`total_tokens=20` 的 `model.completed`
- **THEN** 监控面板可见「用量：输入 12 / 输出 8 / 合计 20」，会话记录区不新增用量行

#### Scenario: 未知用量不显示零

- **WHEN** 当前运行尚无任何已知 token 用量
- **THEN** 监控面板显示「用量：未知」，且 MUST NOT 以「输入 0 / 输出 0」表示未知

#### Scenario: 最近事件带当次用量

- **WHEN** 一次模型调用完成且当次用量已知
- **THEN** 面板最近事件摘要含该次输入与输出 token 数
