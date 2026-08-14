# GUI Agent 基础工具调研

日期：2026-08-14  
范围：在现有 ReAct 工具协议上，用 PyAutoGUI 做最薄的桌面操作层（截图、移鼠、点按、键盘）。本文是调研记录。实现已归档为 `openspec/changes/archive/2026-08-14-desktop-pyautogui-tools/`，主规格见 `openspec/specs/desktop-gui-tools/`。

## 结论

可以做成 GUI Agent，而且不必换框架。现有 `Tool` 协议（名称 + JSON schema + 异步 `invoke` + 确认门）够用。第一批只加 7 个桌面工具，全部走 PyAutoGUI：

| 工具 | 作用 | 默认是否确认 |
| --- | --- | --- |
| `screenshot` | 全屏或区域截图，把图送回下一轮 `think` | 否 |
| `screen_info` | 返回逻辑分辨率与当前鼠标坐标 | 否 |
| `mouse_move` | 移动指针到 `(x, y)` | 否 |
| `mouse_click` | 单击 / 双击 / 右键，可选先移动或按 `target_id` | 是 |
| `mouse_drag` | 从一点拖到另一点 | 是 |
| `mouse_scroll` | 滚轮，正数向上 | 是 |
| `keyboard_type` | 向当前焦点输入文本 | 是 |
| `keyboard_press` | 按下单个键或组合键 | 是 |
| `ocr` | 整图文字识别 | 否 |
| `ocr_locate` | 文字行框 + 编号中心点 | 否 |

截图必须作为多模态 `image_url` 回到模型，不能只回一个文件路径字符串。否则 2B VL 模型看不见屏幕，后续点哪里只能猜。

当前代码做不到这件事：工具结果只是文本，`to_chat_messages` 不会把 tool 消息里的图编进 Chat Completions。GUI 工具落地时要先补这条回注路径。

## 现状

调研当时工作区工具是：`read_file` / `write_file` / `list_dir` / `search_files` / `run_python` / `prepare_image`。第一版 OpenSpec 明确不做完整 OS 自动化。`run_python` 已在 `2026-08-14-remove-run-python-tool` 删除，默认注册表不再暴露代码执行。

做成 GUI Agent 缺三块：

1. 桌面感知：截屏并让 VL 模型看见。
2. 桌面执行：鼠标与键盘。
3. 权限与安全：macOS 辅助功能 / 屏幕录制，以及比写文件更危险的确认策略。

## 为什么用 PyAutoGUI

用户指定 PyAutoGUI。它覆盖截图、移动、点击、拖拽、滚轮、按键，底层截图走 `pyscreeze`，图像用 Pillow（仓库已有）。和现有 `prepare_image` 预处理能直接接上。

代价（在 macOS / Apple Silicon 上必须接受）：

- 需要系统授权：屏幕录制（截图）、辅助功能（键鼠）。未授权时 API 往往静默得到黑图或抛权限错误，工具必须把原因写成中文，而不是空图。
- 坐标系是**逻辑像素**。Retina 上截图像素可能是逻辑分辨率的 2 倍。模型若按截图像素点坐标，再拿去 `moveTo`，会点偏。工具层必须统一成逻辑坐标，并在 `screenshot` / `screen_info` 的返回里写明 `scale`。
- `locateOnScreen` 依赖 OpenCV，定位也不稳，第一批不要做「按图找按钮」。让 VL 模型看图给坐标。
- 调用是同步阻塞。`invoke` 里用 `asyncio.to_thread`，避免卡住 Textual 事件循环。
- 不要让模型通过任意代码执行直接 `import pyautogui`。`run_python` 后来已整工具删除，桌面操作只走桌面工具。

备选（本阶段不采用）：`pynput` 无截图；`mss` 截图更快但键鼠还得另接；macOS 原生 Quartz / AppleScript 能力更强，但会拆成两套 API。第一批保持一个库。

## 建议的最小工具面

命名用英文，与现有 `read_file` 一致。描述和错误用中文。

### 1. `screenshot`

```text
参数：
  region?: { x: int, y: int, width: int, height: int }  // 逻辑像素；缺省全屏
返回（文本摘要 + 图像回注）：
  path, width, height, scale, cursor: {x, y}
```

实现要点：

- `image = pyautogui.screenshot(region=...)`
- 写入 `artifacts/screenshots/<会话id>-<时间戳>.png`（与会话 JSON 一样不进 git）
- 走现有 Pillow 最长边 / 最大字节限制后再给模型
- 全黑或过小的图视为权限失败
- 可选在图上画当前光标十字，降低「点哪里」的歧义

### 2. `screen_info`

```text
返回：screen_width, screen_height, scale, mouse_x, mouse_y
```

对应 `pyautogui.size()`、`pyautogui.position()`。给模型在不截图时做相对移动或校验坐标。

### 3. `mouse_move`

```text
参数：x: int, y: int, duration?: number  // 秒，默认 0.2
```

`pyautogui.moveTo(x, y, duration=...)`。越界应夹紧到屏幕内并在结果里说明，不要抛出图外。

### 4. `mouse_click`

```text
参数：
  button?: "left" | "right" | "middle"   // 默认 left
  clicks?: 1 | 2                         // 默认 1
  x?: int, y?: int                       // 缺省点当前位置
  duration?: number
```

有坐标则先 `moveTo` 再 `click`。这是破坏性操作，走确认门。

### 5. `mouse_drag`

```text
参数：x1, y1, x2, y2, duration?: number, button?: "left"
```

`moveTo(x1,y1)` + `dragTo(x2,y2)`。确认门。

### 6. `keyboard_type`

```text
参数：
  text: string                           // pyautogui.write
  interval?: number
```

只负责写文本，对应 `pyautogui.write`。`write` 模拟按键，不是剪贴板粘贴，对非 ASCII 可能丢字。中文输入第一批可以先走剪贴板粘贴（`pyperclip` + `command+v`），并在 schema 里写清楚。不要在这个工具里接收 `keys`；回车、Tab、热键一律走 `keyboard_press`。

### 7. `keyboard_press`

```text
参数：
  keys: string | string[]                // press 或 hotkey，如 "enter" / ["command","space"]
  interval?: number
```

只负责按键：单个键用 `press`，组合键用 `hotkey`。`keys` 必须做白名单（字母数字、方向键、`enter`/`tab`/`esc`/`backspace`、常见修饰键），禁止任意字符串当键名。不要在这个工具里接收自由文本。

滚轮（`scroll`）可作第二批，不是「能看见就能点」的最小闭环。

## 截图如何回到 Think

这是设计核心，也是和现有文件工具的最大差别。

建议约定：

1. `screenshot` 的 `invoke` 返回短文本摘要（路径、宽高、缩放、光标）。
2. 同一条 tool 消息带上图像引用（本地路径）。
3. `to_chat_messages` 对带图像引用的 tool / assistant 消息编出 `image_url` 部件。
4. 下一轮 `think` 才能根据画面给 `mouse_click` 坐标。

典型闭环：

```text
用户：打开计算器并算 1+1
think → screenshot
observe（图 + 光标）
think → mouse_click(图标)
observe
think → screenshot
...
think → keyboard_type("1+1") → keyboard_press("enter")
think → screenshot → 最终文本回答
```

没有图回注，这个环在 2B 上几乎不可用。

## macOS 约束

目标环境已是 Apple Silicon + Metal。GUI 工具还要满足：

1. **屏幕录制**：系统设置 → 隐私与安全性 → 屏幕录制，勾选运行 `max-gui` 的终端（Terminal / iTerm / VS Code）。否则截图全黑。
2. **辅助功能**：同页的辅助功能，否则键鼠调用失败或无效果。
3. **授权检测**：启动或第一次调用时探测；失败给出可照做的中文步骤，不要只抛英文异常。
4. **Retina**：始终用逻辑坐标；`scale = 截图像素宽 / size()[0]`。
5. **多显示器**：第一批只支持主屏。`screenshot` 默认主屏；多屏坐标以后再做。
6. **TUI 抢焦点**：Agent 在终端里跑，`keyboard_type` / `keyboard_press` 可能打回终端本身。结果里应提示用户先把目标窗口置于前台；第一批可加可选的短暂延迟（`delay_ms`），不要做完整的「按标题找窗」。

## 安全

桌面控制比 `write_file` 危险：可以点系统对话框、发快捷键、把输入打进任意前台窗口。

建议沿用现有确认门，并加严：

- **必须确认**：`mouse_click`、`mouse_drag`、`keyboard_type`、`keyboard_press`。
- **可以不确认**：`screenshot`、`screen_info`、`mouse_move`（只移动）。
- 会话 `auto_approve` 对桌面工具默认不生效，或单独设 `auto_approve_desktop`。避免「批准写文件」连带批准 Command-Q。
- 打开 `pyautogui.FAILSAFE = True`：指针打到屏幕左上角立即中止后续桌面动作。
- 默认 `PAUSE` 约 0.05–0.1s，降低连点打崩 UI 的概率。
- 热键黑名单至少包括关机 / 退出登录相关组合；白名单以外的键名直接拒绝。
- 单回合桌面动作次数设上限（例如 20），防止截图-点击死循环。可复用 `max_iterations`，不必另搞一套。
- 测试用假后端（记录调用、返回夹具图），CI 里不要真动鼠标。

## 建议落地顺序

1. 图像回注：tool 消息可以带图进入 `think`。没有这一步，后面都是盲点。
2. `screen_info` + `screenshot`（含权限错误与缩放）。
3. `mouse_move` + `mouse_click`（确认门 + 逻辑坐标）。
4. `keyboard_type`（写文本）+ `keyboard_press`（白名单按键 / 热键）。
5. `mouse_drag`。
6. 手工场景：截屏 → 点开计算器 → 输入 → 再截屏读结果。

依赖：`pyautogui`（及 `pyscreeze`）；中文粘贴若做，再加 `pyperclip`。不要为第一批引入 OpenCV。

## 明确不做（本调研范围外）

- 按窗口标题切换、枚举控件树、无障碍 API 点按钮
- 浏览器专用 CDP / Playwright（那是另一类 Agent）
- 屏幕录像
- 表格 / 公式 / 图表 / 印章任务与真控件检测（整图 `ocr` 与文字行 `ocr_locate` 已落地，见 `openspec/specs/ocr-tool/`）
- Windows / Linux 一等支持
- 把 vLLM 或 TUI 嵌进被控 GUI 进程

## 落地状态

上述桌面工具已由 OpenSpec change `desktop-pyautogui-tools` 实现并归档。整图 `ocr` 由 `add-ocr-tool` 落地。滚轮、文字定位与视图像素换算由 `add-scroll-locate-and-view-coords` 落地。本文件保留为调研记录，行为以 `openspec/specs/` 为准。
