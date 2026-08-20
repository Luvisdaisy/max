## Why

长思考与多步工具时，用户要等整张 ReAct 图跑完才看到一大段文本。推理虽开了 SSE，思考通道未解析，工具调用也不进记录区，状态栏一直停在「思考中」。 guI Agent 的价值在逐步执行，看不见过程就无法判断卡在思考、点按还是等图。

## What Changes

- SSE 解析 `delta.content` 之外的思考字段（至少 `reasoning_content` / `reasoning`），按增量回调，不并进发给模型的助手正文。
- Agent 在每次 `think` / `act` / `observe` 推进时向外抛进度：思考 token、正文 token、本轮工具调用、每条工具结果、状态名。
- TUI 在 token 到达时写入记录区当前条目；一次 `think` 结束即落成一条助手消息（思考与正文分区）；工具调用与工具结果在执行当时写入记录区，不等整回合结束。
- 状态栏随节点切换（思考中 / 执行工具 / 观察中），不再整回合钉死「思考中」。
- 会话 JSON 在每次 think/act 完成后增量追加消息，时间戳反映真实发生时刻。助手消息可带可选 `reasoning` 字段供回放；编码下一轮请求时 MUST NOT 把 `reasoning` 拼进 `content`。

不包含：像素坐标协议、网格叠加、`ocr_locate` 改图标、新桌面工具、独立 runs 文件。

## Capabilities

### New Capabilities

- （无）

### Modified Capabilities

- `multimodal-inference`：流式解析思考增量并与正文分开回调。
- `react-agent`：图执行期间发出进度事件，think/act 后增量持久化消息。
- `tui-repl`：记录区逐步展示思考、正文、工具调用与工具结果；状态栏跟随节点。
- `session-store`：助手消息可选 `reasoning`；消息按节点增量写入并带各自时间戳。

## Impact

- `src/max_gui/inference/client.py`：SSE 增量字段、`ChatDelta.reasoning`、思考回调。
- `src/max_gui/agent/graph.py`：进度回调、节点后落盘。
- `src/max_gui/app.py`：记录区逐步写入、状态栏、思考样式。
- `src/max_gui/session/store.py`：`reasoning` 与增量 `created_at`。
- 测试：`tests/test_inference.py`、`tests/test_agent.py`、`tests/test_tui.py`、`tests/test_session_store.py`。
