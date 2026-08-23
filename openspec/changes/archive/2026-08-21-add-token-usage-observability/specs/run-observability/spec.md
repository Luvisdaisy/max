## ADDED Requirements

### Requirement: 运行汇总累计 token 用量

`RunRecorder` MUST 把已知的模型调用用量累加到运行汇总的 `prompt_tokens`、`completion_tokens`、`total_tokens`。未知用量的调用 MUST NOT 增加累计值。运行终态事件 MUST 带上该累计；若本次运行没有任何已知用量，这三项 MUST 省略或为 `null`，MUST NOT 写成 0 来表示「没有用量数据」。从既有 JSONL 恢复时 MUST 按同样规则重算累计，以便中断恢复后继续累加。

#### Scenario: 两次已知调用累加

- **WHEN** 一次运行先后产生两次 `model.completed`，用量分别为输入 10/输出 5 与输入 20/输出 7
- **THEN** 终态事件累计 `prompt_tokens` 为 30、`completion_tokens` 为 12、`total_tokens` 为 42

#### Scenario: 未知调用不把累计打成零

- **WHEN** 一次运行只有一次 `model.completed` 且用量未知
- **THEN** 终态事件不含 0 值的三项用量，或这三项为 `null`

#### Scenario: 恢复后继续累加

- **WHEN** 既有运行 JSONL 已有一次已知用量的 `model.completed`，随后从该 `run_id` 恢复并再完成一次已知用量的模型调用
- **THEN** 恢复后的汇总等于两次用量之和
