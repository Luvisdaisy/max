## ADDED Requirements

### Requirement: 执行期工具预算与策略护栏

评测运行器 SHALL 在每个工具请求执行前检查任务定义的工具预算和禁止动作。达到预算或请求禁止动作时，
运行器 MUST 阻止该请求、请求中断当前 Agent，并将任务以可区分的 `tool_limit` 或 `violation` 终态写入结果。
被阻止的动作 MUST 不改变 WebArena 业务状态。

#### Scenario: 工具调用达到上限

- **WHEN** Agent 请求的下一次计费动作将超过该任务的工具上限
- **THEN** 该动作不执行，当前题停止，结果记录 `tool_limit` 与已发生动作数

### Requirement: 隔离且可复现的浏览器条件

评测运行器 SHALL 为每题使用临时、无账号的专用 Chrome profile，并固定窗口尺寸、缩放、语言和统一起始页。
启动器 MUST 在调用 Agent 前确认浏览器与页面可观察，并在题目结束后清理临时 profile。

#### Scenario: 连续两题浏览器隔离

- **WHEN** 第一题改变浏览器本地状态后开始第二题
- **THEN** 第二题使用新的 profile 和统一起始页，不继承第一题的标签页、缓存或页面状态

### Requirement: 可解释且不伪造未知值的评测报告

报告 SHALL 保存运行 manifest，并分别统计计划题、已执行题、环境错误、终止原因、难度、能力与任务族结果。
未知 Token 用量 MUST 在单题保留为 `null`，汇总 MUST 同时报出已知样本数和已知样本 Token 总量，且不得将
未知值计为零。

#### Scenario: 混合已知与未知 Token 用量

- **WHEN** 同一批次中只有部分任务具备 Token 用量
- **THEN** 报告保留未知任务的 `null`，并只用已知任务计算 Token 汇总与样本数
