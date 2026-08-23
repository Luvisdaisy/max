## ADDED Requirements

### Requirement: 默认展示独立运行监控面板

TUI MUST 在会话记录区之外默认展示独立运行监控面板。面板 MUST 显示当前运行编号摘要、状态、当前轮次与上限、当前子任务、活动模型或工具、累计耗时、模型与工具累计耗时、工具成功/失败数和最近运行事件；没有活动运行时 MUST 显示就绪或最近终态。运行监控内容 MUST NOT 作为用户、助手或工具消息写入会话记录区。

#### Scenario: 启动后面板默认可见

- **WHEN** 用户启动 Textual REPL 且尚未提交新任务
- **THEN** 独立运行监控面板已经可见并显示就绪状态

#### Scenario: 工具执行时实时更新

- **WHEN** Agent 发出 `tool.started` 事件
- **THEN** 面板在工具返回前显示当前工具名和执行中状态，会话记录区不新增调试事件行

#### Scenario: 运行完成后保留摘要

- **WHEN** Agent 发出运行终态事件
- **THEN** 面板显示该运行的最终状态、总耗时、调用统计和最近事件

### Requirement: 监控面板隐藏大段敏感正文

监控面板 MUST 只显示事件摘要，MUST NOT 展示完整 reasoning、`keyboard_type` 输入正文、OCR 全文、截图字节、API Key、Authorization Header 或 `.env` 内容。面板 MUST NOT 依赖展示 `artifacts/runs/` 绝对路径来表达运行状态。

#### Scenario: 键盘输入事件只显示工具摘要

- **WHEN** 当前事件来自含正文参数的 `keyboard_type`
- **THEN** 面板可显示工具名、字符数、耗时和结果，但不显示输入正文

### Requirement: 日志写入故障在面板中可见

当运行记录器无法创建或追加 JSONL 时，TUI MUST 在独立监控面板显示中文诊断，且界面 MUST 保持可响应。该诊断 MUST 与 Agent 业务终态分开表达，MUST NOT 把成功完成的任务显示为工具失败。

#### Scenario: 运行文件不可写

- **WHEN** 运行记录器通过内存回调报告写入失败
- **THEN** 面板显示“运行日志写入失败”及安全的错误摘要，用户仍可中断或继续使用 TUI
