## ADDED Requirements

### Requirement: 流式思考与正文分通道

客户端解析 SSE `delta` 时 MUST 把思考增量与正文增量分开。思考字段 MUST 识别 `reasoning_content`，若缺失则识别 `reasoning`。思考增量 MUST 累加到独立的 `reasoning` 缓冲，MUST 通过思考回调交给调用方，MUST NOT 并入正文 `text`，MUST NOT 触发正文 token 回调。无思考字段的流 MUST 与现有正文流式行为一致。

#### Scenario: 思考增量不进入正文

- **WHEN** SSE 先推送 `delta.reasoning_content` 再推送 `delta.content`
- **THEN** 拼好的回复中思考文本在 `reasoning`，正文在 `text`，正文回调未收到思考那段字符串

#### Scenario: 无思考字段仍流式正文

- **WHEN** SSE 只包含 `delta.content`
- **THEN** 客户端按顺序产出正文 token，`reasoning` 为空
