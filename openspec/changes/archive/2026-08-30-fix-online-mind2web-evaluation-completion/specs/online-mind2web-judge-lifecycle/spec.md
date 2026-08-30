## ADDED Requirements

### Requirement: WebJudge 必须由显式请求驱动并回填任务结果

系统 SHALL 仅在用户显式开启 Judge 且提供指定环境变量中的凭据时调用上游 WebJudge。系统 MUST 只提交通过本地
v2 验证的 `result.json`，默认使用单 worker，并将每题 Judge 标签、原始输出、评测模型和错误写入独立结果目录。
凭据 MUST NOT 出现在命令输出、manifest、轨迹、运行日志或报告中。

#### Scenario: 未显式开启 Judge

- **WHEN** 批次完成但用户未请求 WebJudge
- **THEN** 合法轨迹标记为 `judge_pending`，报告标明未判分且不得访问 Judge API

#### Scenario: Judge 成功返回标签

- **WHEN** 用户显式开启 Judge，且至少一条合法轨迹完成评测
- **THEN** 系统回填对应 task id 的标签与原始判词，并将任务标记为 `judged`

#### Scenario: Judge 调用或解析失败

- **WHEN** Judge 子进程非零退出或输出无法关联到任务
- **THEN** 系统保留原始诊断并将受影响任务标记为 `judge_error`，不得把它们计作模型失败

### Requirement: 报告必须表达未判分与各阶段分母

系统 SHALL 分别报告预检 ready、安全阻断、环境不可执行、模型未完成、轨迹有效、Judge pending、Judge error、
已判分和 Judge 成功数量。模型完成率的分母 MUST 为已启动的 ready 任务；Judge 成功率的分母 MUST 为已判分
任务；端到端成功率 MUST 仅在存在 Judge 标签时计算，否则为 `null` 并说明未判分原因。

#### Scenario: 所有任务均未进入 Judge

- **WHEN** 批次没有 Judge 标签
- **THEN** `webjudge_evaluated_tasks` 为 0，Judge 成功率和端到端成功率为 `null`，不得显示为 0 成功率

#### Scenario: 环境与安全终态存在

- **WHEN** 10 条计划任务含 2 条安全阻断、3 条环境不可执行、3 条模型未完成和 2 条已判分任务
- **THEN** 报告分别列出四类数量，Judge 成功率只以 2 条已判分任务为分母
