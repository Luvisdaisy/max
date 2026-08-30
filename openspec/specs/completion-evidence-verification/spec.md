# completion-evidence-verification Specification

## Purpose
TBD - created by archiving change harden-agent-loop-and-session-records. Update Purpose after archive.
## Requirements
### Requirement: 完成声明仅创建待验证证据
桌面副作用任务调用 `task_complete` 且参数有效时，系统 MUST 保存候选 summary、evidence、声明时刻和声明前观察引用，但 MUST NOT 在该工具调用或同一 `observe` 节点设置 `completion_verified=true` 或 `status=done`。

#### Scenario: 声明后仍未完成
- **WHEN** 模型在副作用后的截图存在时调用 `task_complete`
- **THEN** 工具结果标记为待验证，图继续进入验证观察流程而不是结束

### Requirement: 完成声明需要独立后置观察
待验证完成声明存在时，Agent MUST 取得声明之后的新观察截图。校验器 MUST 确认截图文件存在、其时间顺序晚于声明、且可用结构化事实与声明关联；任一条件不满足 MUST 报告中文失败原因并回到 `thinking`。

#### Scenario: 没有声明后的截图
- **WHEN** `task_complete` 后没有成功截图
- **THEN** 会话状态不得为 `done`，模型下一轮收到需要后置观察的原因

#### Scenario: 后置截图缺失
- **WHEN** 声明后的截图路径已不存在
- **THEN** 校验失败并保留待完成状态，不得把模型 summary 当作完成证据

### Requirement: 只有通过独立校验才终止任务
系统 MUST 仅在独立校验通过后调用完成状态迁移，并在任务上下文中保存验证截图引用与校验结论。普通文本、模型 reasoning 或 `task_complete.evidence` 单独均 MUST NOT 构成完成校验。

#### Scenario: 校验通过后结束
- **WHEN** 后置观察通过时间、可用性和结构化事实校验
- **THEN** 图在验证观察后以 `done` 结束，任务上下文含验证结论与截图引用

