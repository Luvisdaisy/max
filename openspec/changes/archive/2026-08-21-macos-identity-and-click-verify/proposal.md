## Why

会话 `20260821-095728` 里，模型在没看到屏幕之前就自称「专门在 Windows 上工作」，并尝试 `Win+R` 打开 Chrome。系统契约只写「本机桌面 GUI Agent」，没有写出真实操作系统，4B 按预训练默认成了 Windows。同一回合里，`mouse_click` 仍要求「上一帧必须来自 `mouse_move`」：模型若先单独 `screenshot` 看光标，点击会被拒；于是它常常 move 完立刻点，红十字并不在 Chrome 上。

## What Changes

- 每次 `think` 的系统消息 MUST 写明当前操作系统（本机为 macOS 时不得自称 Windows 助手），并给出对应快捷键约定（macOS 用 `command`，不要 `windows` / Win+R）。
- macOS 上 `keyboard_press` 的 `windows` 键 MUST 拒绝，并提示改用 `command`。
- **BREAKING（相对上一变更）**：`mouse_click` / `mouse_drag` 在「已经 `mouse_move` 放过光标」的前提下，最近一帧可以是 `mouse_move` 或随后的 `screenshot`。禁止「从没移过鼠就点」。系统契约要求：看到回注图后先判断红十字落在哪个控件上，对了才点，不对再 `mouse_move`。
- 已有视图帧时，系统消息 MUST 带上当前 `view_width`×`view_height`，减少把 Dock 的 y 估到 864 以外。

## Capabilities

### New Capabilities

- （无）

### Modified Capabilities

- `react-agent`：系统契约注入真实 OS、当前视图宽高，以及「看光标再点」。
- `desktop-gui-tools`：点击/拖拽的光标验证允许 move 之后的 screenshot；macOS 拒绝 `windows` 键。
- `agent-tools`：点击前验证规则与上条对齐。

## Impact

- 代码：`src/max_gui/agent/prompts.py`、`agent/graph.py`、`tools/desktop.py` 及对应测试。
- 用户可见：自我介绍不再说 Windows；Win+R 会得到改用 Command 的中文错误；move 后再截一张图不会挡住点击。
- 不改推理后端、不换模型。
