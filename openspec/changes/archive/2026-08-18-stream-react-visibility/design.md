## Context

推理客户端已 `stream: True`，TUI 用 `#live` 接 `on_token`，但整张 LangGraph `ainvoke` 结束才 `_flush_live_stream`，工具结果只进会话 JSON。SSE 只读 `delta.content`。`on_status` 在图启动时叫一次，TUI 未接入。`_persist` 在图结束后一次性追加消息，时间戳相同。

约束：OpenAI 兼容 tool 消息仍须对应 `tool_call_id`；`system` 仍不入会话；RichLog 只能追加，进行中的助手条目继续用 `#live`；不改坐标协议。

## Goals / Non-Goals

**Goals:**

- 思考增量（独立通道）与正文 token 实时可见。
- 每次 `think` 结束即在记录区留下一条助手消息；工具调用与结果在 `act` 当时写入，不等整回合。
- 状态栏跟随 `thinking` / `acting` / `observing`。
- 会话按节点增量落盘；`reasoning` 可回放，但不编进下一轮模型请求。

**Non-Goals:**

- 像素网格、坐标拒绝、图标定位。
- 替换 LangGraph 或 RichLog。
- 把思考并进发给模型的 `content`。
- 独立 `artifacts/runs/`。
- 改 vLLM 启动参数或关闭模型 thinking。

## Decisions

### 1. 思考与正文分通道

`_parse_sse_line` 读取 `delta.reasoning_content` 或 `delta.reasoning`（二者都有时以前者为准）。`ChatDelta` 增加 `reasoning`。`stream()` 增加 `on_reasoning`；思考增量不写入 `assembled.text`，也不调用 `on_token`。

正文仍走 `delta.content` → `on_token`。模型把思考写在 `content` 里、没有独立字段时，只能当正文流式展示，不强行拆 `<think>`。

备选：把思考拼进 `text`。否决原因：污染下一轮上下文，也分不清「想」和「答」。

### 2. Agent 进度回调 + 节点后落盘

`AgentRunner.run` 保留 `on_token`，新增 `on_reasoning`、`on_status`（每个节点进入时调用）、`on_message(role, content)`（一条消息已提交）。

- `think`：流式回调；拼好后立刻 `append_messages` 助手消息（`text` / 可选 `reasoning` / `tool_calls`），再 `on_message`。
- `act`：每执行完一个工具立刻追加该 tool 消息并 `on_message`，不要等本节点全部工具结束。
- 图结束时的 `_persist` 只更新 `status` / `checkpoint` / 坐标系，不再把已追加的消息再写一遍。

TUI 用这些回调画界面，不再等 `ainvoke` 返回后猜最后一条消息。

备选：TUI 轮询会话文件。否决原因：延迟大，还要处理半写 JSON。

### 3. TUI：`#live` 只服务「当前这一次 think」

`#live` 仍承担进行中的思考+正文（思考用暗色前缀「思考」）。一次 `think` 的 `on_message(assistant)` 触发 flush：把 `#live` 落成记录区一条助手消息并清空。随后的工具 `on_message(tool)` 直接 `_write_message`。下一轮 think 重新用空的 `#live`。

回合 `finally` 只 flush 残留（中断时可能还有未提交的 live 文本）。禁止把多轮 think 拼成一条。

恢复会话时：助手若有 `reasoning`，记录区先暗色展示思考再展示正文；无该字段的旧消息行为不变。

状态栏：`thinking` →「思考中…」，`acting` →「执行工具…」，`observing` →「观察中…」，结束态与现在一致。

### 4. `reasoning` 只存在会话 content 里

助手 `content.reasoning` 为可选字符串。`SessionMessage.from_dict` 不丢未知字段（本来就整包 `content`）。`to_chat_messages` 编码 assistant 时只用 `text` 与 `tool_calls`，忽略 `reasoning`。tool 的 `exec` 仍不发给模型。

## Risks / Trade-offs

- [vLLM 不发独立思考字段] → 正文仍按 token 流式；至少工具逐步可见、think 不再整回合才 flush。
- [思考很长撑爆 `#live`] → 保持现有 `max-height` 与滚动；不改布局本期。
- [增量落盘与中断恢复重复追加] → `append_messages` 以当前 `len(session.messages)` 为准；checkpoint 仍整图状态；恢复时从 checkpoint 跑，不把 checkpoint 里的 messages 再 append 一遍（与现逻辑相同：只 append `state.messages[known:]` 中尚未在 session 里的）。
- [确认对话框期间记录区已写「将调用」] → 不提前写「将调用」；`on_message(tool)` 只在 `registry.invoke` 返回后触发，拒绝则写入已取消结果。

## Migration Plan

- 旧会话无 `reasoning` 即可加载。
- 无需数据迁移。回滚：去掉思考解析、进度回调与增量 append，TUI 回到回合结束 flush。

## Open Questions

无。思考不拆 `<think>` 标签；不改 vLLM thinking 开关。
