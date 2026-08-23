## Context

`GUI_SYSTEM_PROMPT` 只说「本机桌面 GUI Agent」，没有操作系统。会话 `20260821-095728` 里 4B 在未见屏幕时自称 Windows 助手，并调用 `keyboard_press(["windows","r"])`。该调用先被「请先截图」拦住，没到键名校验。

上一变更把点击限制成「上一帧必须是 `mouse_move`」。模型若再调 `screenshot` 看光标，验证来源变成 `screenshot`，点击反而被拒。于是它 move 完立刻 `mouse_click`，红十字落在 ChatGPT / 飞书上也会点下去。坐标还经常把 Dock 的 y 估到 `view_height`（864）以外。

## Goals / Non-Goals

**Goals:**

- 系统消息写明真实 OS 与快捷键，自我介绍不再默认 Windows。
- macOS 上拒绝 `windows` 键，提示 `command`。
- 已 `mouse_move` 之后，单独再 `screenshot` 不得挡住点击/拖拽。
- 契约要求先根据图描述红十字落点，对了才点。
- 有视图帧时把宽高写进系统消息。

**Non-Goals:**

- 不自动把 `windows` 映射成 `command`（避免误触）。
- 不视觉识别「红十字是否在 Chrome 上」；4B 仍可能看错，只修协议与文案。
- 不归档上一变更。

## Decisions

### 1. 系统提示按 `platform.system()` 拼 OS 段

`darwin` → 中文「macOS」：你在 macOS 上运行，不是 Windows；开应用用 Dock 或 Spotlight（`command+space`），不要 Win+R；修饰键用 `command` 不是 `windows` 或 `ctrl`（除非应用自己规定）。`Windows` / `Linux` 各写对应一句。该段与固定契约一并注入，仍不写入会话 JSON。

备选是只改固定文案写死 macOS：本仓库主要在 Mac 上跑，但测试机可能是 Linux，写死会骗模型。

### 2. 有视图帧则追加一行宽高

`think` 组装 system 时读 `active_view_frame()`。有帧则追加：「当前截图视图是 {view_width}×{view_height} 像素，坐标必须落在这个范围内。」无帧则不写数字，避免模型拿过期尺寸猜。

### 3. 点击条件改为「移过鼠 + 最近一帧是 move 或 screenshot」

维护 `cursor_placed`：成功 `mouse_move` 置真；成功 `mouse_click` / `mouse_drag` 置假。`mouse_click` / `mouse_drag` 要求 `cursor_placed` 且最近验证来源为 `mouse_move` 或 `screenshot`。这样 move → screenshot → click 合法；从没 move 过、或点完后没再 move 就再点，拒绝。

契约文案：看到回注图后先判断红十字在哪个图标/控件上；只有与目标一致才 `mouse_click`；否则再 `mouse_move`，不要「差不多就点」。

### 4. macOS 拒绝键名 `windows`

在 `_parse_keys` 或按键工具里：`sys.platform == "darwin"` 且键列表含 `windows` 时抛出「本机是 macOS，请使用 command，不要使用 windows」。Linux/Windows 行为不变。`win` 别名同样拒绝。不把 `windows` 加入通用白名单。

## Risks / Trade-offs

- [4B 仍可能看错图标] → 协议只能强迫它先看图再点，不能保证点对。
- [测试在 Linux CI 上跑] → OS 段用 `platform.system()`，测试钉死 darwin 文案时 mock platform。
- [点完后必须再 move 才能再点] → 故意的，避免连点同一错误位置。

## Migration Plan

无数据迁移。旧会话打开即用新 system。

## Open Questions

- 无。
