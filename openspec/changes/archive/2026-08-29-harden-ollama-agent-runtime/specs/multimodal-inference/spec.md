## ADDED Requirements

### Requirement: 推理请求按 token 预算选择上下文

系统 MUST 在发送主推理请求前，按配置的上下文容量扣除输出预留、安全余量和唯一内联图片预留，并对 system、当前用户消息、动态工具 schema 与完整工具调用链进行保守 token 估算。工具调用链 MUST 从最近向前选择，MUST NOT 拆开 assistant `tool_calls` 与对应 tool 消息。当前用户消息、system 与工具 schema 已超过可用预算时 MUST 在网络请求前失败，并给出中文预算诊断。请求 MUST 发送 `max_tokens` 等于配置的输出预留。

#### Scenario: 256K Ollama 请求保留输出空间

- **WHEN** Ollama 上下文容量为 `262144`、输出预留为 `8192`、安全余量为 `4096`
- **THEN** 模型输入选择器不会使用这两项预留，且请求 JSON 的 `max_tokens` 为 `8192`

#### Scenario: 较早完整链被预算裁剪

- **WHEN** 当前用户消息和最近工具链可放入预算，但再加入更早的一条完整链会超限
- **THEN** 请求包含最近完整链，不包含更早完整链，且没有孤立 tool 消息

#### Scenario: 基础请求已超预算

- **WHEN** system、当前用户消息、工具 schema 与图片预留已经超过可用上下文
- **THEN** 客户端不发送 HTTP 请求，并报告容量、预留和估算输入的中文错误

### Requirement: 上下文预算诊断不保存敏感内容

模型调用事件 MUST 记录上下文容量、输出预留、安全余量、估算输入 token、动态工具数量、纳入和裁剪的工具链数量。事件 MUST NOT 复制消息正文、工具 schema、图片内容、键盘输入或完成证据原文。

#### Scenario: 模型事件记录预算计数

- **WHEN** 一次请求从四条完整工具链中按预算选择最近三条
- **THEN** `model.started` 或 `model.completed` 记录纳入三条、裁剪一条及预算数值，且不含工具结果正文
