## ADDED Requirements

### Requirement: 三分钟无步数上限的基线执行

真实桌面基线的每一题 MUST 使用 180 秒执行超时，且系统 MUST NOT 因普通 GUI 动作数量而中断任务。系统仍 MUST
在每个动作前执行任务专属安全白名单，并对个人写入任务保持每轮一次写入请求限制。

#### Scenario: 完成任务需要超过旧动作预算

- **WHEN** Agent 在 180 秒内执行的普通 GUI 动作数超过旧任务定义中的动作预算
- **THEN** 系统不得以动作数为由阻断任务，且继续执行任务专属安全检查

#### Scenario: 180 秒到达

- **WHEN** 一题执行满 180 秒仍未达到 Agent 终态
- **THEN** 系统请求 Agent 温和中断并记录 `timeout` 或 `timeout_forced`，不得继续执行该题的副作用动作

### Requirement: 终态截图的单次独立评审

系统 MUST 在每题执行结束、异常或超时后取得一张当前桌面终态截图；取得截图后 MUST 发起独立、无工具的评审请求。
评审输入 MUST 仅含任务 rubric、运行日期和该截图，且不得包含 Agent 自述、对话、推理或工具轨迹。评审 MUST
最多尝试三次，并仅在无流式输出的可重试错误时指数退避；全部尝试 MUST 复用同一张终态截图。

#### Scenario: 可见完成但未调用完成工具

- **WHEN** 终态截图符合任务 rubric，但 Agent 未调用 `task_complete`
- **THEN** `agent_claimed_complete` 记录为诊断字段，独立评审为 `pass` 且未触发安全违规时任务 MUST 记为成功

#### Scenario: 评审服务限流

- **WHEN** 独立评审请求在无流式输出时返回可重试限流或服务错误
- **THEN** 系统 MUST 最多总尝试三次并采用指数退避；耗尽后记录 `review_error`、请求错误和空的评审 verdict，且不得将该题写为截图评审 `fail` 或任务成功

#### Scenario: 超时后保留人工证据

- **WHEN** 执行超时或温和中断收尾失败
- **THEN** 系统 MUST 尝试保存编排器取得的终态截图，并记录其来源、执行终态和可用运行摘要供人工复核

### Requirement: 单一时间戳记录与自动图表报告

每次 `max --baseline` 成功完成编排后，系统 MUST 仅在
`artifacts/evaluations/baseline-desktop/` 写入一个 `<timestamp>.json` 结果文件，不得在该目录创建本次的批次子目录、
逐题 JSON、Markdown、HTML 或图片。该 JSON MUST 包含本次参数、每题成功记录、执行与评审终态、Token、耗时、步长、
工具统计、安全违规、评审证据与截图/运行日志引用；未知值 MUST 为 `null`。

#### Scenario: 单轮基线完成

- **WHEN** 用户运行一次 `max --baseline`
- **THEN** baseline 目录只新增一个带时间戳的 JSON，且 JSON 包含五题各自的成功结果和全部可用指标

#### Scenario: 自动生成图表报告

- **WHEN** 时间戳 JSON 已原子写入
- **THEN** CLI MUST 调用本地 Python 报告入口，并在 `artifacts/evaluations/baseline-desktop-reports/<timestamp>/` 生成
  从该 JSON 导出的图表和中文摘要；报告生成失败不得删除或修改该 JSON

### Requirement: 可解释的失败与成功汇总

系统 MUST 在单题和批次汇总中分别统计执行失败、超时、安全阻断、截图评审失败、评审不可用与独立评审通过。成功率的
分子 MUST 仅包含未触发安全违规且独立评审 `pass` 的任务；评审不可用与无截图 MUST 单列为不可判定，不能归入截图失败。

#### Scenario: 混合执行和评审终态

- **WHEN** 一个批次同时包含 429 评审错误、超时题和截图评审通过题
- **THEN** 报告 MUST 分别展示这些数量及逐题原因，并使用规定成功公式计算成功率
