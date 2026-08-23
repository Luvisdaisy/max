## ADDED Requirements

### Requirement: 流式补全回传 token 用量

客户端在 `stream` 为真的 `/chat/completions` 请求中 MUST 发送 `stream_options.include_usage` 为真。解析 SSE 时 MUST 读取 payload 级 `usage`（含 `choices` 为空的用量块），并从中取出 `prompt_tokens`、`completion_tokens`、`total_tokens`。用量块 MUST NOT 触发正文或思考 token 回调，MUST NOT 把空 `choices` 当成补全失败。`total_tokens` 缺失但输入与输出均存在时，合计 MUST 等于二者之和。整段流没有可用 `usage` 时，完整回复 MUST 将用量标为未知，MUST NOT 写成 0。提供方忽略 `stream_options` 时 MUST 仍能完成流式正文与工具调用拼装。

#### Scenario: 空 choices 用量块被采纳

- **WHEN** SSE 在正文增量之后推送一块 `choices` 为空且含 `usage.prompt_tokens`、`usage.completion_tokens`、`usage.total_tokens` 的数据
- **THEN** 拼好的回复带有对应三项用量，且正文与思考回调未因该块被再次调用

#### Scenario: 未回传用量则为未知

- **WHEN** 整个 SSE 流只有带 `delta.content` 的块，没有任何 `usage`
- **THEN** 拼好的回复用量为未知，且正文仍按顺序产出

#### Scenario: 请求带 include_usage

- **WHEN** 客户端发起流式 `/chat/completions`
- **THEN** JSON 请求体含 `stream` 为真，且 `stream_options.include_usage` 为真
