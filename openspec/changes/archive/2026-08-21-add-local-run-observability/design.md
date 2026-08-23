## Context

当前 `AgentRunner` 通过 `on_status`、`on_message`、`on_token` 与 `on_reasoning` 直接驱动 TUI，并把助手与工具消息增量写入单个会话 JSON。工具消息已有 `exec` 元数据，但没有一次用户任务的稳定身份、模型与工具的开始事件、严格事件顺序或独立时间线；中间状态也只存在于当前进程。旧规范有意禁止 `artifacts/runs/`，当时目标只是让工具元数据随对话可见，而本次目标扩展为本机实时监控和崩溃后开发排障。

项目仍是单进程、单活跃回合的本地 Textual CLI。用户确认运行监控只服务本机用户；reasoning 与现有工具参数继续持久化；日志只用于开发排障；监控面板默认打开；运行日志无限保留。

## Goals / Non-Goals

**Goals:**

- 为每次用户提交建立可跨中断恢复的 `run_id` 和严格递增事件序列。
- 实时展示状态、轮次、子任务、活动调用、累计耗时、统计摘要和最近事件。
- 把运行事件增量追加到单独 JSONL，使异常退出后仍可阅读已完成部分。
- 保持会话 JSON 是正文、reasoning、工具参数和 checkpoint 的事实来源，避免在事件日志重复大段敏感内容。
- 日志设施失败时给本机用户明确诊断，同时不把开发排障设施变成 Agent 执行的硬依赖。

**Non-Goals:**

- 远程 Dashboard、HTTP/SSE 服务、鉴权、集中日志和跨进程聚合。
- Prometheus、Grafana、OpenTelemetry Collector 或新的消息队列依赖。
- 防篡改审计、合规保留、加密存储或自动清理。
- token 级事件持久化、OCR 全文或截图字节复制。
- 把“取得动作后截图”升级为业务结果验证。

## Decisions

### 1. 会话与运行采用两个身份层级

`session_id` 继续代表长期对话，`run_id` 代表一次用户提交触发的 Agent 执行。新提交创建不依赖第三方库的 UUID 运行编号；同一次运行的 `event_id` 由 `run_id` 与 `sequence` 组合得到。`AgentState` / checkpoint 保存 `run_id`，从 `interrupted` checkpoint 恢复时沿用它并追加 `run.resumed`；普通新回合不得复用上一回合编号。

备选：直接使用 `session_id`。否决原因：一个会话包含多个用户回合，无法隔离单次耗时、终态和统计。

### 2. 新增轻量本地运行事件组件

新增独立的运行可观测性模块，职责分成三个小对象：

- `RunEvent`：版本化、可 JSON 序列化的事件值对象。
- `RunRecorder`：为单次运行分配顺序号、计算单调时钟耗时、追加 JSONL 并维护汇总。
- 事件回调：在同一进程内把事件摘要交给 TUI；不引入通用消息总线框架。

`AgentRunner` 创建或恢复 `RunRecorder`，在既有回调之外增加统一事件回调。旧的 token、reasoning、status 与 message 回调继续保留，避免把流式渲染和会话提交顺手重构为新框架。

备选：让 Python `logging` 文本直接驱动 TUI。否决原因：日志字符串没有稳定 schema，也难以建立消息引用、顺序和运行汇总。

### 3. 事件采用公共信封和有限类型

公共字段至少包含：`schema_version`、`event_id`、`sequence`、带毫秒的本地时区 ISO 时间、`elapsed_ms`、`run_id`、`session_id`、`event_type`、`iteration`、`subtask` 与 `data`。第一版只持久化：

- `run.started`、`run.resumed`、`run.completed`、`run.failed`、`run.interrupted`；
- `state.changed`；
- `model.started`、`model.completed`、`model.failed`；
- `tool.started`、`tool.completed`、`tool.failed`；
- `observation.completed`。

流式 token 和 reasoning token 只走现有内存回调，不逐 token 写 JSONL。`model.completed` 记录耗时、provider、model、finish reason、正文与 reasoning 字符数以及对应会话消息下标。

`tool.started` 必须发生在 `registry.invoke` 前；结束事件发生在工具消息提交会话后，并引用其消息下标。这样未闭合的 started 事件可用于判断异常退出发生在调用过程中。动作后的截图只记作 observation captured，不宣称业务验证成功。

### 4. 每次运行一个追加式 JSONL，写后 flush

运行文件固定为 `artifacts/runs/<run-id>.jsonl`。每条事件占一行 UTF-8 JSON，写入后调用 `flush()`；不为每条事件强制 `fsync()`。恢复运行时读取最后一条合法事件得到下一顺序号；若末尾有异常退出留下的不完整行，保留文件并从最后一条合法事件继续追加。

文件默认无限保留。应用不得按时间、数量或容量自动删除、轮转或压缩会话、运行日志与截图。README 明确说明这些文件会持续增长，且可能包含 reasoning、键盘输入、OCR 结果和截图等敏感信息。

备选：继续重写会话 JSON。否决原因：它无法高效表达开始但未完成的操作，也会把产品历史、checkpoint 与遥测生命周期继续耦合。

### 5. 大段内容只保留在会话 JSON

reasoning 与工具 `exec.arguments` 保持现有会话行为，包括 `keyboard_type` 正文以及过长参数截断规则。运行事件不得复制 reasoning、键盘输入正文、OCR 全文、截图字节或 base64；它通过 `session_message_index` 引用已提交消息，并记录长度、工具名、耗时、结果和图片引用数量等诊断字段。

API Key、Authorization Header 和 `.env` 内容在会话与运行事件中都不得新增记录。该边界减少重复暴露，但不改变用户明确选择的本地明文会话持久化。

### 6. 监控面板默认显示且与会话记录分离

TUI 在记录区之外增加固定的运行监控面板，应用启动后默认可见。面板展示当前运行编号摘要、状态、当前轮次/上限、子任务、活动模型或工具、累计耗时、模型/工具累计耗时、工具成功/失败数和最近事件；没有活动运行时显示就绪与最近终态。

面板只渲染事件摘要，不展示完整 reasoning、键盘输入正文、OCR 全文或 `artifacts/runs/` 路径。现有会话 RichLog、流式助手区和底部状态栏继续工作，工具 `exec` 也仍不作为对话正文。

### 7. 记录失败降级为本地诊断

创建目录、打开文件、序列化或追加失败时，`RunRecorder` 禁用本次运行后续磁盘写入，并通过内存事件回调向监控面板显示“运行日志写入失败”。Agent 继续运行，终态仍写会话 JSON；不得因为开发日志失败而重复执行工具或把正常工具结果改成失败。

备选：日志失败立即终止任务。否决原因：本次日志只用于开发排障，不具备安全审计的强一致性要求。

## Risks / Trade-offs

- [无限保留导致磁盘持续增长] → README 明确风险，第一版不承诺自动清理；用户按需手动删除 `artifacts/` 中对应文件。
- [reasoning 与键盘正文长期明文保存] → 明确这是用户选择的本地开发行为，运行 JSONL 不再复制这些正文，且继续忽略 `artifacts/` 的 Git 跟踪。
- [事件写入增加热路径 I/O] → 每条事件只写一行并 flush，不写 token 事件、不做每条 `fsync()`。
- [事件回调拖慢 Agent] → TUI 回调只调度轻量更新；单个观察者异常必须隔离并转成诊断，不进入工具重试逻辑。
- [崩溃留下 started 无 completed] → 保留未闭合事件作为结果未知的诊断证据；恢复不得因此自动重放桌面动作。
- [会话消息下标因未来迁移变化] → 第一版会话为追加式列表，下标稳定；事件同时保存 `session_id` 和消息角色用于校验。
- [状态栏和监控面板内容重复] → 状态栏保持一句当前状态，监控面板承担结构化进度与最近事件。

## Migration Plan

1. 增加事件模型、运行记录器及其单元测试，不读取或改写旧会话。
2. 为 `AgentRunner` 增加运行身份和事件边界，保持现有回调兼容。
3. 接入默认打开的 TUI 监控面板并补行为测试。
4. 更新 README 的目录、无限保留和敏感信息说明。
5. 旧会话缺少 `run_id` 时正常加载；只有新的或明确中断后保存的新 checkpoint 才具备运行恢复关联。

回滚时可停止创建和读取 `artifacts/runs/`，移除面板和事件回调；既有 JSONL 是独立诊断文件，不影响旧会话加载，可由用户手动保留或删除。

## Open Questions

无。监控范围、reasoning 持久化、开发排障定位、独立面板默认显示、无限保留和键盘正文保留均已由用户确认。
