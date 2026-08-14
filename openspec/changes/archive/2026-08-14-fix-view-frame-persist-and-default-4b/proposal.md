## Why

实测会话里，截图成功后下一句用户话再移鼠标会回「尚无截图，按逻辑像素」，因为视图坐标系只活在当次 worker 的 `ContextVar` 里。同时截图摘要把逻辑光标标成 `coordinate_space=view`，流式 HTTP 失败会抛出 httpx 内部文案，盖住真正状态码。2B 看图与猜坐标都不稳，本机已有 4B 权重，默认挂载应切过去。

## What Changes

- 成功 `screenshot` / `ocr_locate` 的坐标系与定位编号写入会话 JSON，每回合开始恢复；跨用户回合仍按视图像素换算。
- 截图摘要中的 `cursor` 改为视图像素；`region` 在 schema 中标明为逻辑像素。
- 流式客户端在 HTTP 非 2xx 时读取响应正文，TUI 展示状态码与截断 body，不再出现 `without having called read()`。
- **BREAKING（默认模型）**：未指定 `--model` / `MAX_GUI_MODEL` 时，默认别名从 `qwen3.5-2b` 改为 `qwen3.5-4b`。`2b` / `4b` / `9b` 别名仍可用。测试夹具可继续钉死 2B。

## Capabilities

### New Capabilities

- （无）

### Modified Capabilities

- `desktop-gui-tools`：视图坐标系与定位编号必须跨回合保留；摘要 `cursor` 必须是视图像素。
- `session-store`：会话 JSON 持久化最近一次截图坐标系与 `ocr_locate` 命中表。
- `multimodal-inference`：流式错误必须可读；默认模型改为 4B。

## Impact

- `src/max_gui/tools/desktop.py`、`src/max_gui/session/store.py`、`src/max_gui/agent/graph.py`
- `src/max_gui/inference/client.py`、`src/max_gui/config.py`、`src/max_gui/cli.py`
- `tests/test_tools.py`、`tests/test_session_store.py`、`tests/test_inference.py`、`tests/test_cli.py`、`tests/test_agent.py`
- `AGENTS.md`、`README.md`、主规格 `openspec/specs/`
