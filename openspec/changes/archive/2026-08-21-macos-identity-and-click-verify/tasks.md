## 1. 系统契约标明真实 OS 与视图尺寸

- [x] 1.1 按 `platform.system()` 拼 OS 段；macOS 写明不是 Windows，快捷键用 command
- [x] 1.2 `think` 注入 system 时，若有视图帧则写入当前 view_width×view_height
- [x] 1.3 契约要求：看回注图判断红十字落点，对了才 click
- [x] 1.4 更新 `test_think_injects_system_not_persisted` 及 OS / 视图宽高用例

## 2. 点击验证与 windows 键

- [x] 2.1 `cursor_placed`：成功 mouse_move 置真，成功 click/drag 置假；click/drag 要求已放置且最近一帧为 move 或 screenshot
- [x] 2.2 macOS 上 `keyboard_press` 拒绝 `windows` / `win`，提示改用 command
- [x] 2.3 测试：move 后再 screenshot 可点击；点完未再 move 则拒绝；darwin 上拒绝 Win+R

## 3. 收尾

- [x] 3.1 `uv run ruff format src tests` 与 `uv run ruff check src tests`
- [x] 3.2 跑 `tests/test_agent.py`、`tests/test_tools.py`、`tests/test_plan.py`
