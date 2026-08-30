# run-observability Specification

## Purpose

规定本地单用户 GUI Agent 的运行身份、结构化事件、JSONL 持久化和 TUI 监控边界，使运行状态可观察且不泄露敏感正文。
## Requirements
### Requirement: 为每次用户任务建立运行身份

系统 MUST 为每次新的用户文本提交创建不同于会话编号的 `run_id`。一次运行中产生的所有事件 MUST 使用同一 `run_id`；从已中断 checkpoint 恢复时 MUST 沿用原 `run_id` 并追加 `run.resumed`，MUST NOT 把恢复误记为全新任务。

#### Scenario: 同一会话内两个任务使用不同运行编号

- **WHEN** 用户在同一会话中先后提交两个普通文本回合
- **THEN** 两个回合的事件使用相同 `session_id` 和不同 `run_id`

### Requirement: 运行事件具有稳定信封与严格顺序

每条持久化事件 MUST 包含 `schema_version`、`event_id`、`sequence`、`timestamp`、`elapsed_ms`、`run_id`、`session_id`、`event_type`、`iteration`、`subtask` 与对象类型的 `data`。同一运行内 `sequence` MUST 从 1 开始严格递增，`event_id` MUST 能由运行编号和顺序号唯一定位；`timestamp` MUST 带本地时区并至少精确到毫秒，耗时 MUST 使用单调时钟计算。

#### Scenario: 快速连续事件仍可排序

- **WHEN** 同一毫秒内产生两个运行事件
- **THEN** 后一个事件的 `sequence` 大于前一个事件，二者 `event_id` 不同

### Requirement: 增量追加本地运行日志

系统 MUST 把每次运行的事件按产生顺序写入 `artifacts/runs/<run-id>.jsonl`，每行 MUST 是一个完整 UTF-8 JSON 对象，并在每条事件后刷新用户态写缓冲。事件 MUST 在运行过程中增量写入，MUST NOT 等到运行终态后一次性生成。异常退出留下的不完整末行 MUST NOT 阻止读取此前合法事件或恢复后继续追加。

#### Scenario: 异常末行不破坏已有轨迹

- **WHEN** 运行文件末尾存在一个不完整 JSON 行，前面存在合法事件
- **THEN** 系统仍能读取前面的合法事件，并从最后一个合法顺序号之后恢复追加

### Requirement: 运行日志无限保留

系统 MUST 默认无限保留运行 JSONL，MUST NOT 按时间、文件数量、总容量或应用启动次数自动删除、轮转、压缩或覆盖既有运行文件。系统 MUST 在项目说明中告知用户运行日志、会话与截图会持续占用磁盘并可能含敏感信息。

#### Scenario: 启动时保留旧运行文件

- **WHEN** `artifacts/runs/` 已含任意时间创建的合法运行文件且应用再次启动
- **THEN** 应用不删除、重命名、压缩或截断该文件

### Requirement: 事件引用会话中的大段内容

模型和工具完成事件 MUST 在对应消息已提交会话后记录 `session_message_index`。运行事件 MUST NOT 复制 reasoning 原文、`keyboard_type` 输入正文、OCR 全文、截图字节或 base64；允许记录字符数、工具名、耗时、结果、图片数量和消息引用。运行事件 MUST NOT 新增记录 API Key、Authorization Header 或 `.env` 内容。

#### Scenario: reasoning 只在会话中保存一份

- **WHEN** 模型完成事件对应的助手消息含 reasoning
- **THEN** 会话 JSON 保留 reasoning 原文，运行事件只含消息下标与 reasoning 字符数而不含原文

### Requirement: 汇总运行诊断数据

运行终态事件 MUST 包含运行总耗时、迭代数、模型调用数及累计耗时、工具调用数及累计耗时、工具成功数、工具失败数和最终状态。取得动作后截图只能记录为观察已捕获，MUST NOT 在没有独立验证结论时记录为业务验证成功。

#### Scenario: 正常完成时给出汇总

- **WHEN** 一次运行经过模型和工具调用后正常完成
- **THEN** `run.completed` 的 `data` 含模型、工具、迭代和总耗时汇总，最终状态为 `done`

### Requirement: 运行日志故障不阻断 Agent

创建目录、打开文件、序列化或追加事件失败时，系统 MUST 停止本次运行后续磁盘事件写入，并 MUST 通过本机内存回调报告中文诊断。Agent MUST 继续执行并按原行为保存会话终态；日志故障 MUST NOT 触发工具重试、重复桌面动作或把成功的工具结果改成失败。

#### Scenario: 运行目录不可写时继续任务

- **WHEN** 系统无法创建或写入当前运行 JSONL
- **THEN** TUI 监控面板显示运行日志写入失败，Agent 仍可完成当前任务并保存会话结果

### Requirement: 运行监控保持本地边界

第一版运行可观测性 MUST 只使用当前进程回调和本地文件，MUST NOT 因此启动 HTTP、SSE、WebSocket 或其它网络监听服务，也 MUST NOT 要求外部日志、指标或追踪服务才能运行。

#### Scenario: 离线环境可使用监控

- **WHEN** 用户在没有可用网络和外部监控服务的本机启动 TUI
- **THEN** 实时监控与运行 JSONL 仍可工作，且系统未为监控功能监听网络端口

### Requirement: 运行汇总累计 token 用量

`RunRecorder` MUST 把已知的模型调用用量累加到运行汇总的 `prompt_tokens`、`completion_tokens`、`total_tokens`。未知用量的调用 MUST NOT 增加累计值。运行终态事件 MUST 带上该累计；若本次运行没有任何已知用量，这三项 MUST 省略或为 `null`，MUST NOT 写成 0 来表示「没有用量数据」。从既有 JSONL 恢复时 MUST 按同样规则重算累计，以便中断恢复后继续累加。

#### Scenario: 两次已知调用累加

- **WHEN** 一次运行先后产生两次 `model.completed`，用量分别为输入 10/输出 5 与输入 20/输出 7
- **THEN** 终态事件累计 `prompt_tokens` 为 30、`completion_tokens` 为 12、`total_tokens` 为 42

#### Scenario: 未知调用不把累计打成零

- **WHEN** 一次运行只有一次 `model.completed` 且用量未知
- **THEN** 终态事件不含 0 值的三项用量，或这三项为 `null`

#### Scenario: 恢复后继续累加

- **WHEN** 既有运行 JSONL 已有一次已知用量的 `model.completed`，随后从该 `run_id` 恢复并再完成一次已知用量的模型调用
- **THEN** 恢复后的汇总等于两次用量之和

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

### Requirement: 运行终态提供会话可投影诊断
运行记录器 MUST 在终态汇总中提供稳定的 `terminal_reason` 和最后一次模型 `finish_reason`。`terminal_reason` MUST 至少区分正常完成、迭代上限、恢复耗尽、推理失败和用户中断；未知模型结束原因 MUST 为 `null` 或省略。该汇总 MUST 不复制消息、reasoning、OCR 全文或截图字节。

#### Scenario: 恢复耗尽具有独立终态原因
- **WHEN** Agent 因重复失败恢复上限而结束
- **THEN** `run.failed` 的汇总含 `terminal_reason="recovery_exhausted"`，且会话可安全投影该值

#### Scenario: 正常完成不伪造模型结束原因
- **WHEN** 运行正常完成但 provider 没有返回 `finish_reason`
- **THEN** 终态汇总仍为正常完成，最后模型结束原因省略或为 `null`，不得写成虚构值
