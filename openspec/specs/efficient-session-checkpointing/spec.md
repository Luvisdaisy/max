# efficient-session-checkpointing Specification

## Purpose
TBD - created by archiving change harden-agent-loop-and-session-records. Update Purpose after archive.
## Requirements
### Requirement: 会话消息只有一个持久化副本
新写入会话 MUST 仅在顶层 `messages` 保存完整用户、助手和工具消息。checkpoint MUST 使用非负 `message_cursor` 标识已纳入运行状态的顶层消息数量，MUST NOT 包含 `messages` 字段或消息正文副本。

#### Scenario: 新会话结束后无重复历史
- **WHEN** 一个含工具循环的新会话保存 checkpoint
- **THEN** 顶层 `messages` 含完整历史，checkpoint 含 `message_cursor` 且不含 `messages`

### Requirement: 游标 checkpoint 可恢复并兼容旧记录
恢复新格式 checkpoint 时，系统 MUST 从顶层 `messages` 的前 `message_cursor` 条重建图消息。游标越界或消息损坏时 MUST 安全降级为不可恢复状态并保留可读历史。旧 checkpoint 含 `messages` 而无游标时 MUST 仍可加载，不得丢失其可恢复状态。

#### Scenario: 中断的新格式会话恢复
- **WHEN** 中断会话的 checkpoint 指向合法消息游标
- **THEN** 恢复后的图消息顺序与顶层会话消息一致，且不复制消息正文

### Requirement: 会话保存紧凑运行摘要和观察引用
每次运行终态后，会话 MUST 保存 `run_summary`，至少含 `run_id`、最终状态、终态原因、迭代数、模型/工具成功失败计数、累计耗时、已知 token 用量和最后模型 `finish_reason`（未知时为 `null`）。大型 locate 候选框明细 MUST 不重复写入 checkpoint 或摘要；会话消息仅保存帧引用、候选数和可读摘要。

#### Scenario: 会话可独立诊断终态
- **WHEN** 运行因迭代上限、恢复耗尽、推理失败、中断或正常完成结束
- **THEN** 会话 `run_summary` 能区分该终态原因，不依赖读取完整 JSONL

