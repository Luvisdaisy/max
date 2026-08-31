## RENAMED Requirements

- FROM: `### Requirement: 三分钟无步数上限的基线执行`
- TO: `### Requirement: 五分钟或二十次模型调用上限的基线执行`

## MODIFIED Requirements

### Requirement: 五分钟或二十次模型调用上限的基线执行

真实桌面基线的每一题 MUST 最多执行 5 分钟或 20 次 Agent 逻辑模型调用，并以先达到的限制终止执行。provider 内部重试
和独立评审 AI 调用 MUST NOT 计入 20 次额度。系统 MUST NOT 因普通 GUI 动作数量而中断任务；任务字段
`timeout_seconds` MUST 固定为 300，并同时作为执行终止值和评分时间参考值。

#### Scenario: 达到五分钟执行时限

- **WHEN** Agent 运行达到 300 秒且尚未达到 20 次逻辑模型调用
- **THEN** 系统先请求温和中断，有限收尾后必要时强制取消，并记录 `timeout` 或 `timeout_forced`

#### Scenario: 达到执行模型调用额度

- **WHEN** 同一任务准备发起第 21 次 Agent 逻辑模型调用
- **THEN** 系统停止该任务并记录 `model_limit`，provider 内部重试和独立评审 AI 不增加该计数

### Requirement: 终态截图的单次独立评审

系统 MUST 在每题正常结束、异常、执行超时或达到模型调用上限后取得一张当前桌面终态截图；取得截图后 MUST 发起独立、无工具的
评审请求。评审输入 MUST 仅含任务 rubric、运行日期和该截图，且不得包含 Agent 自述、对话、推理或工具轨迹。评审 MUST
最多尝试三次，并仅在无流式输出的可重试错误时指数退避；全部尝试 MUST 复用同一张终态截图。

所有 baseline 评审 MUST 固定使用 provider 注册表中的 Qiniu provider、模型、端点和上下文窗口，并 MUST 使用
`MAX_QINIU_KEY` 鉴权，与执行 Agent 的 provider/model 配置隔离。系统 MUST 在执行首题前校验 Qiniu 密钥；缺失时 MUST
直接失败，不得产生桌面副作用。评审客户端 MUST 为 `z-ai/glm-5.3-flash` 发送
`thinking.type=enabled` 与 `reasoning_effort=low`，不得携带工具或向控制台输出 reasoning；其调用和重试 MUST NOT
增加执行 `model_calls`。

#### Scenario: 可见完成但未调用完成工具

- **WHEN** 终态截图符合任务 rubric，但 Agent 未调用 `task_complete`
- **THEN** `agent_claimed_complete` 记录为诊断字段，独立评审为 `pass` 时任务 MUST 记为成功

#### Scenario: 评审服务限流

- **WHEN** 独立评审请求在无流式输出时返回可重试限流或服务错误
- **THEN** 系统 MUST 最多总尝试三次并采用指数退避；耗尽后记录 `review_error`、请求错误和空的评审 verdict，且不得将该题写为截图评审 `fail` 或任务成功

#### Scenario: 不同执行模型使用同一裁判

- **WHEN** 用户分别以不同执行 provider 或 model 运行 baseline
- **THEN** 每次评审均使用 Qiniu 注册模型，运行记录同时保存执行与评审 provider/model

#### Scenario: 强制思考评审模型使用最低档位

- **WHEN** 系统调用 Qiniu `z-ai/glm-5.3-flash` 评审终态截图
- **THEN** 请求携带 `thinking.type=enabled` 和 `reasoning_effort=low`，控制台只显示最终评审正文而不显示 reasoning

#### Scenario: 缺少统一评审密钥

- **WHEN** 启动 baseline 时未设置有效的 `MAX_QINIU_KEY`
- **THEN** 系统在首题执行前以中文凭据错误停止，不得启动 Agent 或执行桌面动作

#### Scenario: 模型调用上限后保留人工证据

- **WHEN** 执行 Agent 达到 20 次逻辑模型调用仍未完成
- **THEN** 系统 MUST 尝试保存编排器取得的终态截图，并记录其来源、执行终态和可用运行摘要供人工复核

#### Scenario: 执行超时后自动评审

- **WHEN** 执行达到 5 分钟并以 `timeout` 或 `timeout_forced` 终止
- **THEN** 系统 MUST 截取当前桌面并自动调用独立评审 AI，不得因执行超时跳过评审

### Requirement: 单一时间戳记录与显式多模型报告

每次 `max --baseline` 成功完成编排后，系统 MUST 仅在
`artifacts/evaluations/baseline-desktop/` 写入一个 `<timestamp>.json` 结果文件，不得自动调用报告入口或在报告目录生成任何
文件。该 JSON MUST 包含本次执行及评审 provider/model 参数、每题成功记录、执行与评审终态、执行模型调用次数、Token、耗时、步长、工具统计、评审证据、截图/运行
日志引用、版本化总分及其分项；未知值 MUST 为 `null`，且 MUST NOT 包含 violation 字段。

#### Scenario: 单轮基线完成

- **WHEN** 用户运行一次 `max --baseline`
- **THEN** baseline 目录只新增一个带时间戳的 JSON，且 JSON 包含五题各自的成功结果和全部可用指标，不包含 violation 字段

#### Scenario: 显式生成多模型报告

- **WHEN** 用户用 1–5 份运行 JSON 执行 `max --baseline -report`
- **THEN** 系统 MUST 生成 `report.md` 与 `charts/*.png`，表格按输入顺序保留各运行一行且行名只显示模型名，表格与图表均不得展示评审 Token

#### Scenario: 相同模型存在多次运行

- **WHEN** 报告输入包含两份 model 字段相同的运行 JSON
- **THEN** Markdown MUST 按输入顺序保留两行相同模型名，所有对应柱使用相同颜色，并在表格外列出输入源路径供区分

### Requirement: 版本化 baseline 任务与批次总分

系统 MUST 在每个可执行任务结束后使用 `baseline-score-v2` 计算 0–100 分，并在写入运行 JSON 前保存总分、完整性、缺失指标、
固定参考值和所有分项。环境或用户确认阻断总分 MUST 为 `null`。各分项 MUST 为：

- 效果 70 分：`pass=70`、`indeterminate=35`、`fail`、`review_error` 或无截图为 0；
- 执行时间 10 分：`10 × clamp(1 - execution_duration_ms / timeout_ms, 0, 1)`；
- 动作步长 5 分：`5 × clamp(1 - actions / 10, 0, 1)`；
- 工具调用 5 分：`5 × clamp(1 - tool_calls / 15, 0, 1)`；
- 工具可靠性 5 分：`5 × (1 - tool_failures / max(tool_calls, 1))`；
- 执行 Token 5 分：`5 × clamp(1 - execution_tokens / 100000, 0, 1)`。

总分 MUST 四舍五入到两位。任一必需效率指标未知时，该分项和总分 MUST 为 `null`，不得将未知值记零或重新分配权重。
完整批次的 `overall_score` MUST 为所有可测题总分的算术平均；存在未测或无总分任务时 MUST 为 `null`，并同时保存
`score_coverage` 与算法版本。评分 MUST NOT 包含 violation 硬门槛。

#### Scenario: 评审通过且指标完整

- **WHEN** 一题评审为 `pass`，且耗时、动作、工具调用/失败和执行 Token 均已知
- **THEN** 系统 MUST 按固定公式写入六个分项与两位小数总分，并标记 `complete=true`

#### Scenario: 必需指标未知

- **WHEN** 一题已执行但执行 Token 或其它必需效率指标为 `null`
- **THEN** 系统 MUST 将对应分项和总分写为 `null`，列出缺失指标，并标记 `complete=false`

#### Scenario: 批次未覆盖全部任务

- **WHEN** 一轮存在环境阻断、用户跳过或无总分任务
- **THEN** 批次 `overall_score` MUST 为 `null`，并以 `score_coverage` 如实表示有完整分数的任务比例

### Requirement: 可解释的失败与成功汇总

系统 MUST 在单题和批次汇总中分别统计执行失败、模型调用上限、环境/用户阻断、截图评审失败、评审不可用与独立评审
通过。成功率的分子 MUST 仅包含独立评审 `pass` 的任务；评审不可用与无截图 MUST 单列为不可判定，不能归入截图失败。
系统 MUST NOT 生成 violation 终态或统计。

#### Scenario: 混合执行和评审终态

- **WHEN** 一个批次同时包含 429 评审错误、模型调用上限题和截图评审通过题
- **THEN** 报告 MUST 分别展示这些数量及逐题原因，并使用规定成功公式计算成功率

## ADDED Requirements

### Requirement: baseline 向每题开放受控注册工具

系统 MUST 向每个 baseline 执行 Agent 暴露当前 `ToolRegistry` 中除 `activate_app`、`click` 外的全部工具，并 MUST NOT
按任务类型、导航行为或输入文本执行任务专用 guard。被排除工具 MUST NOT 出现在模型 schema 或 Act 节点允许集合中。
工具注册表自身的参数校验、确认门和 Agent 通用执行约束 MUST 保持生效。普通 TUI 和其它评测 MUST 继续使用原有动态工具
暴露策略。

#### Scenario: 每题获得受控工具 schema

- **WHEN** 任一 baseline 任务启动执行 Agent
- **THEN** 发送给模型的工具 schema 覆盖当前注册表中除 `activate_app`、`click` 外的全部工具

#### Scenario: 任务调用任意已注册工具

- **WHEN** Terminal、Reminders 或 WeChat 任务调用任意已开放工具并通过工具自身参数校验
- **THEN** baseline 不得因任务类型、导航行为或输入文本拒绝该调用或生成 violation

### Requirement: baseline 启动信息可核对

系统 MUST 在 baseline 启动且参数有效后、执行首题前输出当前执行模型的 provider 与 model 名称，且 MUST NOT 输出 API Key。

#### Scenario: 启动真实桌面基线

- **WHEN** 用户启动参数有效的 baseline
- **THEN** 终端在首题确认和执行前显示执行 provider 与 model 名称
