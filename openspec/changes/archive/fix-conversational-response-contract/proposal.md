## Why

当前 GUI system 要求模型在正文中输出包含 `thought` 与文本 `tool_calls` 的 JSON，但运行时已经使用原生工具调用。模型因此把长思考和协议 JSON 写入用户可见正文，简单对话没有可读的正式回复。

## What Changes

- 取消正文严格 JSON 与文本 `tool_calls` 合同，工具仅通过现有 OpenAI 兼容 native tool calling 返回。
- 定义面向用户的回复规则：普通对话直接简短回答；GUI 任务在执行中只给短状态，完成时给明确结果。
- 明确禁止把内部思考、计划推演或协议 JSON 写入普通 `content`；仅提供方的独立 reasoning 字段仍按现有逻辑显示为思考。
- 调整 TUI 和 Agent 测试，覆盖普通对话输出与工具调用消息展示。

## Capabilities

### New Capabilities

- （无）

### Modified Capabilities

- `react-agent`：GUI system 的正文输出与原生工具调用契约。
- `tui-repl`：普通助手正文与独立 reasoning 的展示边界。

## Impact

- `src/max_gui/agent/prompts.py`：简化用户可见输出合同。
- `src/max_gui/agent/graph.py`、`src/max_gui/app.py`：仅在必要处保证正文按现有通道显示。
- `tests/test_agent.py`、`tests/test_tui.py`：回归验证。
