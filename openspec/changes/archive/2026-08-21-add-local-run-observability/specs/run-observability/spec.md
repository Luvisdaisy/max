## ADDED Requirements

### Requirement: 为每次用户任务建立运行身份

系统 MUST 为每次新的用户文本提交创建不同于会话编号的 `run_id`。一次运行中产生的所有事件 MUST 使用同一 `run_id`；从已中断 checkpoint 恢复时 MUST 沿用原 `run_id` 并追加 `run.resumed`，MUST NOT 把恢复误记为全新任务。

#### Scenario: 同一会话内两个任务使用不同运行编号

- **WHEN** 用户在同一会话中先后提交两个普通文本回合
- **THEN** 两个回合的事件使用相同 `session_id` 和不同 `run_id`

#### Scenario: 中断恢复沿用运行编号

- **WHEN** 一次运行以 `interrupted` 保存 checkpoint，随后用户恢复该运行
- **THEN** 恢复事件与中断前事件使用相同 `run_id`，且新事件中包含 `run.resumed`

### Requirement: 运行事件具有稳定信封与严格顺序

每条持久化事件 MUST 包含 `schema_version`、`event_id`、`sequence`、`timestamp`、`elapsed_ms`、`run_id`、`session_id`、`event_type`、`iteration`、`subtask` 与对象类型的 `data`。同一运行内 `sequence` MUST 从 1 开始严格递增，`event_id` MUST 能由运行编号和顺序号唯一定位；`timestamp` MUST 带本地时区并至少精确到毫秒，耗时 MUST 使用单调时钟计算。

#### Scenario: 快速连续事件仍可排序

- **WHEN** 同一毫秒内产生两个运行事件
- **THEN** 后一个事件的 `sequence` 大于前一个事件，二者 `event_id` 不同

### Requirement: 增量追加本地运行日志

系统 MUST 把每次运行的事件按产生顺序写入 `artifacts/runs/<run-id>.jsonl`，每行 MUST 是一个完整 UTF-8 JSON 对象，并在每条事件后刷新用户态写缓冲。事件 MUST 在运行过程中增量写入，MUST NOT 等到运行终态后一次性生成。异常退出留下的不完整末行 MUST NOT 阻止读取此前合法事件或恢复后继续追加。

#### Scenario: 工具尚未完成时已有开始事件

- **WHEN** `tool.started` 已产生但工具调用仍未返回
- **THEN** 对应运行 JSONL 已包含该开始事件

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

#### Scenario: 键盘正文不复制到运行日志

- **WHEN** `keyboard_type` 的工具消息在会话 `exec.arguments` 中含输入正文
- **THEN** 工具完成事件引用该消息但不包含输入正文本身

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
