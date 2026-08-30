## ADDED Requirements

### Requirement: 运行终态提供会话可投影诊断
运行记录器 MUST 在终态汇总中提供稳定的 `terminal_reason` 和最后一次模型 `finish_reason`。`terminal_reason` MUST 至少区分正常完成、迭代上限、恢复耗尽、推理失败和用户中断；未知模型结束原因 MUST 为 `null` 或省略。该汇总 MUST 不复制消息、reasoning、OCR 全文或截图字节。

#### Scenario: 恢复耗尽具有独立终态原因
- **WHEN** Agent 因重复失败恢复上限而结束
- **THEN** `run.failed` 的汇总含 `terminal_reason="recovery_exhausted"`，且会话可安全投影该值

#### Scenario: 正常完成不伪造模型结束原因
- **WHEN** 运行正常完成但 provider 没有返回 `finish_reason`
- **THEN** 终态汇总仍为正常完成，最后模型结束原因省略或为 `null`，不得写成虚构值
