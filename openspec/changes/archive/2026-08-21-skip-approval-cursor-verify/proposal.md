## Why

会话 `20260821-095256` 暴露了四件会直接导致桌面任务失败的事：每次点击都要人点「允许」；模型凭目测直接 `mouse_click`，坐标经常点偏；`screenshot` 的 `region` 可以大于主屏，把视图坐标系写成 2560×1440，真实逻辑屏却是 1920×1080，于是视图像素 `y=780~855` 被换算后夹紧到约 `647`；多轮 ReAct 后 `think` 抛错，会话仍标 `done`，检查点停在第一回合，错误正文没有落盘。

## What Changes

- **BREAKING**：所有已注册工具默认不再弹出确认。`mouse_click` / `mouse_drag` / `mouse_scroll` / `keyboard_type` / `keyboard_press` / `write_file` 的 `confirmation_scope` 改为 `none`。会话仍可保留 `auto_approve` 字段，但不再作为执行前提。
- **BREAKING**：点击、拖拽、键盘输入不得在未验证光标的情况下直接带着坐标执行。`mouse_move` 必须移动后立刻回注带光标标注的截图；`mouse_click` 只点当前位置，不再接受 `x`/`y` 并立刻按下；`mouse_drag` 以当前位置为起点；`keyboard_type` / `keyboard_press` 在输入前必须已有一帧能看到当前光标/焦点的截图，否则拒绝并要求先 `mouse_move` 或 `screenshot`。
- `screenshot` 的 `region` 必须夹紧到主屏逻辑范围内，视图坐标系的逻辑宽高必须与实际截到的区域一致，禁止再用模型猜的超界宽高污染后续换算。
- `think` 调用推理失败时，会话状态必须记为 `error` 并写入可读错误，不得继续显示上一回合的 `done` 与过期检查点。
- 发给主模型的回注图从「最近两张」改为「最近一张」，降低 `max_model_len=8192` 下多轮带图请求顶满上下文的概率。

## Capabilities

### New Capabilities

- （无）

### Modified Capabilities

- `agent-tools`：取消破坏性工具确认；点击不再带坐标直接按下。
- `desktop-gui-tools`：光标先移动再截图验证；点击只点当前位置；拖拽从当前位置开始；截图区域夹紧到主屏。
- `tui-repl`：TUI 不再为工具弹出确认框。
- `session-store`：`auto_approve` / `auto_approve_desktop` 不再控制是否执行工具；思考失败必须写入会话错误状态。
- `react-agent`：系统契约改为「先移鼠并看光标再点/拖/输入」；推理异常必须落盘。
- `multimodal-inference`：每个请求只回注最近一张仍存在的图。

## Impact

- 代码：`src/max_gui/tools/desktop.py`、`files.py`、`registry.py`、`app.py`、`agent/prompts.py`、`agent/graph.py`、`inference/client.py`、`session/store.py`。
- 测试：确认门、带坐标点击、两张图回注、会话默认批准字段等相关用例要改预期。
- 用户可见：TUI 不再出现「允许执行 mouse_click？」；Agent 打开 Dock 图标的流程变为移鼠 → 看光标 → 再点。
- 不改推理服务本身的 `max_model_len`；不引入新工具名。
