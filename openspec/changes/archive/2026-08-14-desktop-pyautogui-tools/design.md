## Context

第一版已有统一 `Tool` 协议、确认门、LangGraph ReAct，以及用户消息的图像编码。工具结果目前只是字符串：`Tool.invoke` 返回 `str`，`to_chat_messages` 把 tool 消息当纯文本。桌面闭环缺两块：PyAutoGUI 执行层，以及截图作为多模态 tool 结果回到 `think`。

调研记录见 `docs/gui-tools.md`。本变更在现有协议上加最薄的桌面层，不换框架。

约束：macOS Apple Silicon、Python 3.12、`uv`、Textual 事件循环不能被同步键鼠调用卡住、CI 不得真动鼠标。

## Goals / Non-Goals

**Goals:**

- 注册 7 个桌面工具，全部走 PyAutoGUI：`screenshot`、`screen_info`、`mouse_move`、`mouse_click`、`mouse_drag`、`keyboard_type`、`keyboard_press`
- 截图以 `image_url` 进入下一轮 `think`
- 统一逻辑像素坐标，返回 Retina `scale`
- 破坏性桌面动作走独立确认门，不被会话 `auto_approve` 连带批准
- macOS 权限失败给出可照做的中文步骤
- 测试用假后端，CI 不调用真实 PyAutoGUI

**Non-Goals:**

- 按窗口标题切前台、枚举控件树、无障碍点击
- 浏览器 CDP / Playwright
- 屏幕录像、OCR、`locateOnScreen` / OpenCV
- 滚轮（`scroll`）与多显示器一等支持
- Windows / Linux 一等支持
- 把 vLLM 或 TUI 嵌进被控 GUI 进程

## Decisions

### 1. 保留现有 Tool 协议，扩展返回值而不是新框架

`Tool` 仍是名称 + JSON schema + 异步 `invoke` + 确认标记。`invoke` 从只返回 `str` 扩展为可返回结构化结果：

```text
ToolResult(text: str, images: list[Path] = [])
```

`act` 把结果写成与用户消息同形的 tool 消息：

```text
{
  "role": "tool",
  "tool_call_id": "...",
  "name": "screenshot",
  "content": {"text": "<摘要>", "images": [{"path": "..."}]}
}
```

纯文本工具继续返回 `str`，`registry` 兼容两种返回值。不引入第二套工具系统。

- 备选：只把路径写进文本，让模型自己 `read_file`。不采用：2B VL 看不见图。
- 备选：截图当用户消息追加。不采用：破坏 tool_call 配对。

### 2. `to_chat_messages` 给 tool 消息编图像

`role == "tool"` 时：若 `content` 是带 `images` 的对象，则编出文本部件 + `image_url` 部件（复用 `prepare_image` 的边长 / 字节限制）；否则保持现有字符串行为。assistant 消息若将来带图，走同一规则。

这是 GUI 闭环的前提，必须先于真实键鼠落地，并有单测覆盖。

### 3. 一个桌面后端接口，生产走 PyAutoGUI，测试走假后端

新增 `DesktopBackend` 协议，方法对应工具动作（`screenshot`、`size`、`position`、`move_to`、`click`、`drag_to`、`write`、`press`、`hotkey`）。生产实现包装 PyAutoGUI，在 `asyncio.to_thread` 中调用。测试实现记录调用并返回夹具图。

注册工具时注入 backend。默认 `pyautogui.FAILSAFE = True`，`PAUSE` 约 `0.05`。不要为第一批引入 OpenCV。

同步 API 不得直接在 Textual 事件循环里跑。

### 4. 逻辑坐标与主屏

所有输入坐标是逻辑像素。越界夹紧到 `size()` 范围内，并在结果里说明。`scale = 截图像素宽 / size()[0]`，写进 `screenshot` 与 `screen_info`。第一批只操作主屏；`region` 也按逻辑像素解释。

可选在截图上画当前光标十字，降低 2B「点哪里」的歧义；默认开启。

### 5. 键盘拆成写与按

- `keyboard_type(text, interval?, delay_ms?)`：只写文本。ASCII 走 `write`；含非 ASCII 时走剪贴板粘贴（`pyperclip` + `command+v`），schema 描述写清楚。不接收 `keys`。
- `keyboard_press(keys, interval?, delay_ms?)`：只按键。单键 `press`，多键 `hotkey`。键名白名单：字母数字、方向键、`enter`/`tab`/`esc`/`backspace`/`space`/`delete`，以及 `command`/`shift`/`ctrl`/`alt`/`option`。白名单外直接拒绝。热键黑名单至少包括关机 / 退出登录相关组合（如 `command+q`、`command+shift+q`、`command+option+esc`）。不接收自由文本。

两者都支持可选 `delay_ms`，给用户把目标窗口置前的时间。结果里提示：输入会打到当前前台窗口，可能是终端本身。

### 6. 确认策略与会话开关分离

| 工具 | 确认 | 普通 `auto_approve` | `auto_approve_desktop` |
| --- | --- | --- | --- |
| `screenshot` / `screen_info` / `mouse_move` | 否 | — | — |
| `mouse_click` / `mouse_drag` / `keyboard_type` / `keyboard_press` | 是 | 不生效 | 可跳过 |
| `write_file` / `run_python` | 是 | 可跳过 | 不生效 |

`Tool` 增加 `confirmation_scope`: `workspace` | `desktop` | `none`。TUI 确认门按 scope 读对应会话字段。避免「批准写文件」连带批准 Command-Q。

单回合桌面动作次数不另设上限，复用已有 `max_iterations`。

### 7. 权限探测与中文错误

第一次桌面调用前探测屏幕录制与辅助功能。截图全黑或过小视为屏幕录制失败。键鼠权限错误写成中文步骤：系统设置 → 隐私与安全性 → 屏幕录制 / 辅助功能，勾选运行 `max-gui` 的终端。不要把英文异常原文丢给用户。

截图写入 `artifacts/screenshots/<会话id>-<时间戳>.png`，目录加入 gitignore（与会话 JSON 一样）。

### 8. 禁止经 `run_python` 绕过

`run_python` 在执行前用 AST 拒绝导入 `pyautogui`、`pyscreeze`、`pynput` 及 `from X import ...` 的等价写法。命中则返回中文权限错误，不启动子进程。工作区脚本仍可跑，只是不能当桌面后门。

## Risks / Trade-offs

- [Risk] Retina 下模型按截图像素点坐标 → 夹紧 + 返回 `scale`，schema / 摘要写明「使用逻辑坐标」。
- [Risk] `write` 丢中文 → 非 ASCII 走剪贴板粘贴；可能覆盖用户剪贴板。
- [Risk] 键盘打回 TUI 终端 → `delay_ms` + 结果提示；第一批不做按标题找窗。
- [Risk] 未授权时 PyAutoGUI 静默黑图 → 全黑/过小检测 + 中文权限文案。
- [Risk] 热键误触系统退出 → 白名单 + 关机/登出黑名单 + 独立确认门。
- [Risk] 同步 PyAutoGUI 卡住 TUI → 一律 `asyncio.to_thread`。
- [Risk] CI 真动鼠标 → 默认假后端；集成测试标记为本地手工。

## Migration Plan

- 依赖：`pyautogui`；`keyboard_type` 的非 ASCII 路径加 `pyperclip`。
- 会话 JSON 新增可选 `auto_approve_desktop`，缺省 `false`；旧会话无需迁移。
- `Tool.invoke` 返回值向后兼容 `str`。
- 回滚：不注册桌面工具即可回到纯工作区 Agent；会话多一个未读字段无害。

## Open Questions

- 光标十字默认开还是做成 `screenshot` 参数：本设计默认开，可用 `show_cursor=false` 关闭。
- 非 ASCII 粘贴是否每次都覆盖剪贴板：接受，并在工具描述中写明。
