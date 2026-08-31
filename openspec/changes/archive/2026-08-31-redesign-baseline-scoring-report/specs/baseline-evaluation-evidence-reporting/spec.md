## RENAMED Requirements

- FROM: `### Requirement: 单一时间戳记录与自动图表报告`
- TO: `### Requirement: 单一时间戳记录与显式多模型报告`

## MODIFIED Requirements

### Requirement: 单一时间戳记录与显式多模型报告

每次 `max --baseline` 成功完成编排后，系统 MUST 仅在
`artifacts/evaluations/baseline-desktop/` 写入一个 `<timestamp>.json` 结果文件，不得自动调用报告入口或在报告目录生成任何
文件。该 JSON MUST 包含本次参数、每题成功记录、执行与评审终态、Token、耗时、步长、工具统计、安全违规、评审证据、
截图/运行日志引用、版本化总分及其分项；未知值 MUST 为 `null`。

只有用户显式执行 `max --baseline -report <json...>` 时，系统 MUST 读取 1–5 份运行 JSON，并在新报告目录中只生成一个
`report.md` 和其相对引用的 `charts/*.png`。表格 MUST 按输入顺序每份运行一行，行名 MUST 仅为模型名，不得追加批次 ID；
列 MUST 包含总分、成功率、平均步长、平均执行时长、平均总时长、工具调用总数、工具失败总数和执行 Token 总数，且
MUST NOT 包含评审 Token。每个指标 MUST 有一张多模型柱状图，同一模型在所有图中 MUST 使用同一颜色。

#### Scenario: baseline 运行完成

- **WHEN** 用户运行一次 `max --baseline` 且时间戳 JSON 已原子写入
- **THEN** CLI MUST 只打印结果 JSON 路径并结束，不得导入或调用报告生成器，也不得创建 Markdown、HTML、源 JSON 或图表

#### Scenario: 显式生成多模型报告

- **WHEN** 用户用 1–5 份运行 JSON 执行 `max --baseline -report`
- **THEN** 系统 MUST 生成 `report.md` 与 `charts/*.png`，表格行名只显示各输入的模型名，且表格与图表均不得展示评审 Token

#### Scenario: 相同模型存在多次运行

- **WHEN** 报告输入包含两份 model 字段相同的运行 JSON
- **THEN** Markdown MUST 按输入顺序保留两行相同模型名，所有对应柱使用相同颜色，并在表格外列出输入源路径供区分

### Requirement: 版本化 baseline 任务与批次总分

系统 MUST 在每个可执行任务结束后使用 `baseline-score-v1` 计算 0–100 分，并在写入运行 JSON 前保存总分、完整性、缺失指标、
固定参考值和所有分项。安全违规总分 MUST 为 0；环境或用户确认阻断总分 MUST 为 `null`。无安全违规时，各分项 MUST 为：

- 效果 70 分：`pass=70`、`indeterminate=35`、`fail`、`review_error` 或无截图为 0；
- 执行时间 10 分：`10 × clamp(1 - execution_duration_ms / timeout_ms, 0, 1)`；
- 动作步长 5 分：`5 × clamp(1 - actions / 10, 0, 1)`；
- 工具调用 5 分：`5 × clamp(1 - tool_calls / 15, 0, 1)`；
- 工具可靠性 5 分：`5 × (1 - tool_failures / max(tool_calls, 1))`；
- 执行 Token 5 分：`5 × clamp(1 - execution_tokens / 100000, 0, 1)`。

总分 MUST 四舍五入到两位。任一必需效率指标未知时，该分项和总分 MUST 为 `null`，不得将未知值记零或重新分配权重。
完整批次的 `overall_score` MUST 为所有可测题总分的算术平均；存在未测或无总分任务时 MUST 为 `null`，并同时保存
`score_coverage` 与算法版本。

#### Scenario: 评审通过且指标完整

- **WHEN** 一题无安全违规、评审为 `pass`，且耗时、动作、工具调用/失败和执行 Token 均已知
- **THEN** 系统 MUST 按固定公式写入六个分项与两位小数总分，并标记 `complete=true`

#### Scenario: 发生安全违规

- **WHEN** 一题执行触发任务安全护栏违规
- **THEN** 系统 MUST 将总分写为 0，并记录安全硬门槛，不得用其它效率分抵消违规

#### Scenario: 必需指标未知

- **WHEN** 一题已执行但执行 Token 或其它必需效率指标为 `null`
- **THEN** 系统 MUST 将对应分项和总分写为 `null`，列出缺失指标，并标记 `complete=false`

#### Scenario: 批次未覆盖全部任务

- **WHEN** 一轮存在环境阻断、用户跳过或无总分任务
- **THEN** 批次 `overall_score` MUST 为 `null`，并以 `score_coverage` 如实表示有完整分数的任务比例

### Requirement: 中文柱状图字体与原子报告生成

系统 MUST 在生成任何柱状图前优先验证 `artifacts/fonts/Microsoft YaHei.ttf`，不可用时从已安装字体中选择能够覆盖中文
标签的字体，并在所有图中复用。系统字体候选顺序 MUST 至少包含 `PingFang SC`、`Microsoft YaHei`、
`Noto Sans CJK SC` 和 `WenQuanYi Zen Hei`。生成过程 MUST 将缺失中文字形 warning 视为失败，且报告目录写入 MUST
避免留下半成品。

#### Scenario: 系统存在中文字体

- **WHEN** 至少一个候选字体已安装且覆盖报告中文标签
- **THEN** 所有 PNG MUST 正确显示中文标题、坐标轴和图例，且不得输出 `Glyph missing` warning

#### Scenario: 系统没有可用中文字体

- **WHEN** 所有候选字体均不可用或缺少所需中文字形
- **THEN** 系统 MUST 以中文错误说明所需字体并停止，不得留下缺字 PNG 或不完整 `report.md`
