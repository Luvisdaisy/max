## Why

当前运行日志和 TUI 监控面板能回答一次任务耗时多久、调了几次模型与工具，但看不到每次补全实际消耗了多少 token。云端按量计费、本地上下文窗口也会被悄悄打满，用户无法在本机实时判断本轮输入、输出和累计用量。现有流式解析还会丢掉 OpenAI 兼容接口在空 `choices` 块中回传的 `usage`。

## What Changes

- 流式 `/chat/completions` 请求启用用量回传（`stream_options.include_usage`），并从 SSE 中解析 `usage`，包括没有 `choices` 的用量块。
- 将每次模型调用的输入、输出、合计 token 写入 `model.completed`；运行终态汇总累计用量。提供方未回传时记录为未知，MUST NOT 把缺失当成 0。
- `RunRecorder` 在恢复既有 JSONL 时累加已知用量；不新增事件类型，不逐 token 写日志。
- TUI 独立运行监控面板展示本次运行的累计输入/输出/合计 token，以及最近一次模型调用的用量；会话记录区仍不写入用量调试行。
- 不估算本地 tokenizer、不展示费用、不把用量写入会话 JSON 正文。

## Capabilities

### New Capabilities

- 无。用量统计建立在已有运行可观测性之上，不引入新能力域。

### Modified Capabilities

- `multimodal-inference`: 请求并解析流式补全的 token 用量，缺失时安全降级。
- `react-agent`: 把模型调用用量写入运行事件，不复制正文或 reasoning。
- `run-observability`: 在模型完成事件与运行终态汇总中持久化 token 用量。
- `tui-repl`: 在默认运行监控面板展示累计与最近一次模型调用的 token 用量。

## Impact

- `src/max_gui/inference/client.py`：请求 `include_usage`，解析 SSE `usage`，`ChatDelta` 携带用量字段。
- `src/max_gui/agent/graph.py`：`model.completed` 写入每次调用的用量。
- `src/max_gui/observability/recorder.py`：累计 `prompt_tokens` / `completion_tokens` / `total_tokens`，恢复时一并还原。
- `src/max_gui/app.py`：监控面板与最近事件摘要展示用量。
- `tests/test_inference.py`、`tests/test_observability.py`、`tests/test_agent.py`、`tests/test_tui.py`：覆盖解析、汇总、未知用量与面板展示。
- `README.md`：说明监控面板可见 token 用量，以及提供方未回传时显示未知。
- 不新增第三方依赖，不增加网络监听，不改变会话 JSON schema。
