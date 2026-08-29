## ADDED Requirements

### Requirement: 运行事件记录模型重试

每次即将重新发送主推理请求前，Agent MUST 发出 `model.retrying` 事件。事件 MUST 包含当前网络尝试序号、最大尝试数、稳定原因码、可选 HTTP 状态码、下一次等待毫秒和安全错误摘要，MUST NOT 包含请求消息、响应正文全文、图片、工具 schema、Authorization 或 API Key。最终 `model.completed` 或 `model.failed` MUST 包含 `attempt_count` 与 `retry_count`。TUI MUST 用中文显示重试进度和等待时间。

#### Scenario: 两次失败后成功的事件顺序

- **WHEN** 一次逻辑模型调用前两次失败且第三次成功
- **THEN** 运行日志依次含一个 `model.started`、两个 `model.retrying` 和一个 `model.completed`，终态事件的 `attempt_count` 为 3、`retry_count` 为 2

#### Scenario: 重试耗尽的事件顺序

- **WHEN** 默认策略下 6 次网络尝试全部失败
- **THEN** 运行日志含 5 个 `model.retrying` 和一个 `model.failed`，失败事件的 `attempt_count` 为 6、`retry_count` 为 5

#### Scenario: 重试事件不泄露请求内容

- **WHEN** 请求含截图、键盘输入、工具 schema 与认证头且发生重试
- **THEN** `model.retrying` 只保存规定的诊断元数据，不复制这些敏感内容

### Requirement: 重试保持逻辑模型调用统计

一次 `think` 中的全部网络尝试 MUST 统计为一次逻辑模型调用。运行汇总的模型调用次数 MUST NOT 因重试增加，模型耗时 MUST 包含全部网络尝试和退避等待，token 用量 MUST 只累计成功最终响应返回的 usage。

#### Scenario: 三次网络尝试只算一次模型调用

- **WHEN** 一次 `think` 在第三次网络尝试成功
- **THEN** 运行汇总的 `model_calls` 增加 1，耗时覆盖三次尝试与两次等待，token 只累计第三次响应
