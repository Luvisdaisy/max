## ADDED Requirements

### Requirement: checkpoint 不得复制会话历史
新格式会话的 checkpoint MUST 以 `message_cursor` 引用顶层 `messages`，并保存恢复所需的运行状态；MUST NOT 复制完整消息列表、reasoning 原文、工具输出或图像引用。旧 checkpoint 含 `messages` 的会话 MUST 仍可加载，下一次成功保存时 MAY 写为新格式。

#### Scenario: 新 checkpoint 使用游标
- **WHEN** Agent 在一条新会话消息后保存 checkpoint
- **THEN** checkpoint 以游标引用该消息，且文件中不存在第二份同一消息内容

#### Scenario: 旧 checkpoint 正常加载
- **WHEN** 旧会话 checkpoint 含完整 `messages` 且无 `message_cursor`
- **THEN** SessionStore 仍能加载会话和恢复状态

### Requirement: 会话记录运行终态摘要
会话 JSON MUST 在每个运行终态后写入紧凑 `run_summary`。摘要 MUST 包含运行身份、最终状态、终态原因、迭代数、模型与工具计数/累计耗时、已知 token 用量和最后模型结束原因；未知值 MUST 为 `null` 或省略，MUST NOT 伪造成功数据。

#### Scenario: 推理失败写入可审计摘要
- **WHEN** think 因推理失败终止
- **THEN** 会话 `run_summary` 的最终状态为 `error`，终态原因与最后可用结束原因可区分于正常完成
