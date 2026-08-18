## ADDED Requirements

### Requirement: 助手消息可带思考原文

会话 JSON 中 `role=assistant` 的 `content` MUST 允许可选字符串字段 `reasoning`。缺少该字段的旧消息 MUST 仍能加载。重新打开会话时，若存在 `reasoning`，记录区 MUST 能展示这段思考（与正文分区）。编码发给模型时 MUST NOT 把 `reasoning` 作为助手 `content` 正文。

#### Scenario: 带思考字段恢复

- **WHEN** 已存助手消息含非空 `reasoning` 与 `text`
- **THEN** 重新加载后记录区可见该思考文本，且后续 think 请求的该条助手消息正文不含 `reasoning` 字符串

#### Scenario: 旧消息缺字段

- **WHEN** 已存助手消息没有 `reasoning`
- **THEN** 会话仍能加载，记录区只展示原有正文

### Requirement: 消息按节点增量写入

在同一用户回合内，助手消息与 tool 消息 MUST 在对应节点完成时写入会话文件，各自 `created_at` MUST 为该次写入时刻。MUST NOT 把同一回合全部消息拖到图结束再用同一个时间戳一次性写入。

#### Scenario: 工具循环中途时间戳已不同

- **WHEN** 助手先请求工具、随后 tool 结果写入
- **THEN** 会话 JSON 中该 tool 消息的 `created_at` 不早于对应助手消息的 `created_at`
