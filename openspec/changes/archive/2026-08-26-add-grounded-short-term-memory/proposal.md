## Why

当前 Agent 会把近期完整工具调用链发送给模型，并持久化 `locate_hits`，但任务胶囊只保留工具名称和成败。模型无法稳定知道某个控件的定位编号、该编号所属截图及其可执行状态，容易在同一界面重复调用 `locate`。同时，旧截图坐标不能在新画面继续使用，否则会破坏高 DPI 与动态界面的点击安全约束。

## What Changes

- 新增任务级“已落地短期事实记忆”：以简短、脱敏的事实保存可复用的定位目标、动作核验结论及其来源截图。
- 为定位句柄增加与当前截图帧绑定的生命周期；新截图生成后使旧定位事实和可执行编号失效。
- 将仍然有效的事实以有限、模型可读的摘要注入下一次 `think`，引导模型复用 `target_id`，而非重复定位。
- 调整 GUI 系统契约：仅在当前帧没有有效定位时调用 `locate`；移动后依据回注截图决定是否无参数点击。
- 持久化短期事实记忆，并保证旧会话和旧 checkpoint 能安全降级加载。

## Capabilities

### New Capabilities

- `grounded-short-term-memory`：管理任务内、带来源和失效条件的可复用 GUI 事实，并生成受限的模型摘要。

### Modified Capabilities

- `react-agent`：模型上下文和系统契约需要包含有效短期事实，且不得重放失效定位信息。
- `desktop-gui-tools`：当前截图刷新时，定位编号和对应事实需要按帧一致地失效。
- `session-store`：会话与 checkpoint 需要保存兼容的任务级短期事实记忆。

## Impact

- 代码：`src/max_gui/agent/context.py`、`graph.py`、`prompts.py`、`src/max_gui/tools/desktop.py`、`locate.py`、`src/max_gui/session/store.py`。
- 测试：`tests/test_agent.py`、`test_tools.py`、`test_locate.py`、`test_session_store.py`。
- 不新增外部服务、数据库或模型依赖；仍使用现有本地 JSON 会话文件。
