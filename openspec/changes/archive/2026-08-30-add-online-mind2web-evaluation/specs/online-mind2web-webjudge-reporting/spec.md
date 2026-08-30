## ADDED Requirements

### Requirement: 在本地验证后显式调用 WebJudge

系统 SHALL 仅在任务轨迹通过 v2 本地验证且用户显式提供独立评测凭据后调用上游 WebJudge。调用 MUST
默认串行执行，并保存评测器模型、阈值、原始判词、每题标签和评测错误；不得将凭据写入 manifest、轨迹、
运行日志或仓库文件。

#### Scenario: 未提供评测凭据

- **WHEN** 用户请求生成轨迹但未配置 WebJudge 凭据
- **THEN** 系统完成本地轨迹与汇总导出，并标明 WebJudge 未运行，不访问评测 API

#### Scenario: WebJudge 判分完成

- **WHEN** 合法轨迹使用显式凭据完成 WebJudge 调用
- **THEN** 系统将成功或失败标签、原始判词和评测模型写入独立结果目录，并关联对应 task id

### Requirement: 分离报告环境、模型、安全与评测器结果

系统 SHALL 输出 JSON 和 Markdown 汇总，分别报告计划任务数、ready 数、环境不可执行数、安全阻断数、
已执行任务数、WebJudge 成功率、耗时、工具调用、已知 Token 用量与相对动作效率。模型任务成功率的
分母 MUST 只包含 ready 且完成执行的任务；全计划端到端成功率 MUST 使用全部计划任务为分母。

#### Scenario: 环境失败不降低模型成功率

- **WHEN** 10 条计划任务中 2 条在预检时因 CAPTCHA 不可执行，8 条完成 WebJudge 且 4 条成功
- **THEN** 报告模型任务成功率为 4/8，全计划端到端成功率为 4/10，并单独列出 2 条 CAPTCHA 任务

#### Scenario: 未知 Token 用量保持未知

- **WHEN** 某次任务运行没有完整的模型 Token 用量
- **THEN** 单题和汇总将该用量标记为 `null` 或未知样本，不得用 0 代替
