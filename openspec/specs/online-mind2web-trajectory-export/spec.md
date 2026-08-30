# online-mind2web-trajectory-export Specification

## Purpose
TBD - created by archiving change add-online-mind2web-evaluation. Update Purpose after archive.
## Requirements
### Requirement: 导出自包含的 Online-Mind2Web v2 任务轨迹

系统 SHALL 为每个已执行任务在独立目录写入 `result.json` 和 `trajectory/` 截图文件，且 `result.json` MUST
使用 `online-mind2web-v2`。每个步骤 MUST 原子关联连续的零基 `step`、存在的截图文件名、事实性 action、
显式存在的 `thought` 键和当前 URL；最终步骤 MUST 为 `TASK_COMPLETE`，其答案与顶层
`agent_final_answer` 一致。`reference_length` MUST 使用上游人类参考步数，MUST NOT 使用 Agent 实际步数。

#### Scenario: 成功动作形成可审计步骤

- **WHEN** Agent 在任务中完成一个可映射的真实网页动作并获得对应观察
- **THEN** 系统以同一已解析坐标系保存动作、URL、截图和思考，并使截图路径在任务目录中可解析

#### Scenario: 轨迹结构不合法

- **WHEN** 任一步骤缺截图、step 不连续、缺 `thought` 键、最终动作不是 `TASK_COMPLETE` 或最终答案不一致
- **THEN** 系统拒绝该任务的正式导出和 WebJudge 调用，并把验证错误写入任务结果

### Requirement: 轨迹与普通运行日志保持不同的隐私边界

系统 SHALL 仅向评测轨迹导出器提供完成动作映射所需的结构化信息。普通运行 JSONL MUST 继续不记录
reasoning 原文、键盘输入正文、截图字节、Cookie、认证信息或 API Key。若输入内容不由任务显式要求或匹配
敏感模式，系统 MUST 中止该题的轨迹导出并标记安全事件。

#### Scenario: 普通运行日志不扩展敏感内容

- **WHEN** Online-Mind2Web 任务执行键盘输入并生成评测步骤
- **THEN** 评测导出器按策略生成事实性 `TYPE` 动作，而通用运行 JSONL 不新增输入正文

#### Scenario: 检测到敏感输入

- **WHEN** Agent 尝试输入任务未要求的疑似密码、支付信息或个人标识
- **THEN** 系统阻止后续执行，记录安全事件，且不把该任务记为模型失败

