## 1. 工具结果回注

- [x] 1.1 扩展 `Tool` / `registry`：`invoke` 可返回 `str` 或带 `text` + 图像路径的结构化结果；`act` 写入 tool 消息
- [x] 1.2 扩展 `to_chat_messages`：对带图像引用的 tool / assistant 消息编出文本 + `image_url` 部件，复用现有预处理
- [x] 1.3 为纯文本 tool 结果、带图 tool 结果、缺图路径补充单元测试

## 2. 确认门与会话字段

- [x] 2.1 `Tool` 增加 `confirmation_scope`（`workspace` / `desktop` / `none`）；`write_file` / `run_python` 标为 workspace
- [x] 2.2 会话增加并持久化 `auto_approve_desktop`，缺省 `false`；旧 JSON 缺字段视为关闭
- [x] 2.3 TUI 确认门按 scope 读取对应开关；普通 `auto_approve` 不放行桌面工具
- [x] 2.4 覆盖：工作区自动批准仍确认点击；桌面自动批准跳过按键；拒绝则不执行

## 3. 桌面后端

- [x] 3.1 加入 `pyautogui` 与 `pyperclip` 依赖；`artifacts/screenshots/` 不进 git
- [x] 3.2 定义 `DesktopBackend` 协议；实现记录调用、返回夹具图的假后端
- [x] 3.3 实现 PyAutoGUI 后端：`asyncio.to_thread`、`FAILSAFE`、`PAUSE`、逻辑坐标夹紧、`scale`
- [x] 3.4 权限探测：黑图/过小视为屏幕录制失败；键鼠权限失败返回中文步骤

## 4. 桌面工具

- [x] 4.1 实现 `screen_info` 与 `screenshot`（主屏 / `region`、光标十字、图像回注），无需确认
- [x] 4.2 实现 `mouse_move`（无需确认）与需确认的 `mouse_click`、`mouse_drag`
- [x] 4.3 实现 `keyboard_type`（ASCII `write`，非 ASCII 剪贴板粘贴）与 `keyboard_press`（白名单 / 危险热键黑名单）
- [x] 4.4 将 7 个工具注册进默认表；`run_python` 用 AST 拒绝导入 `pyautogui` / `pyscreeze` / `pynput`
- [x] 4.5 用假后端测试：截图回注、夹紧、确认拒绝、键名拒绝、危险热键拒绝、禁止 `import pyautogui`

## 5. 验收

- [x] 5.1 跑聚焦单测（不要求真动鼠标、不要求 GPU）
- [x] 5.2 手工过一遍：授权提示、截屏 → 点击 → `keyboard_type` → `keyboard_press` → 再截屏读结果
