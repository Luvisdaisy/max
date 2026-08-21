## 1. 取消工具确认

- [x] 1.1 将 `write_file` 与桌面破坏性工具的 `confirmation_scope` 改为 `none`
- [x] 1.2 TUI 确认门对所有工具直接放行，不再弹出 `ConfirmScreen`
- [x] 1.3 更新确认相关测试：未开自动批准时点击、写文件、按键均立即执行

## 2. 光标验证协议

- [x] 2.1 `mouse_move` 成功后按 `screenshot` 规则回注带光标标注的截图并更新视图帧
- [x] 2.2 `mouse_click` 拒绝 `x`/`y`/`target_id`，只点当前位置；无最近 `mouse_move` 截图则拒绝
- [x] 2.3 `mouse_drag` 以当前位置为起点，只接受 `x2`/`y2`；无最近 `mouse_move` 截图则拒绝
- [x] 2.4 `keyboard_type` / `keyboard_press` 在本会话尚无 `screenshot` 或 `mouse_move` 截图时拒绝
- [x] 2.5 更新 `GUI_SYSTEM_PROMPT`：先移鼠看光标，再无坐标点击/拖拽/输入
- [x] 2.6 更新桌面工具测试与 schema 断言

## 3. 坐标系与截图区域

- [x] 3.1 `screenshot` 将 `region` 夹紧到主屏，逻辑宽高用夹紧后的值
- [x] 3.2 `active_view_frame` 优先读会话进程缓存，避免父 ContextVar 盖住后置截图
- [x] 3.3 增加测试：超界 region 不写入 2560×1440；后置全屏截图覆盖错误帧

## 4. 多轮推理失败可见

- [x] 4.1 `think` 捕获推理异常，状态设为 `error` 并让 `run` 正常 persist
- [x] 4.2 `MAX_INLINE_IMAGES` 改为 1，历史图改路径摘要
- [x] 4.3 增加测试：stream 抛错后面会话 `status=error`；两张历史图只回注最后一张

## 5. 收尾

- [x] 5.1 `uv run ruff format src tests` 与 `uv run ruff check src tests`
- [x] 5.2 跑受影响的 `tests/test_tools.py`、`tests/test_tui.py`、`tests/test_agent.py`、`tests/test_inference.py`、`tests/test_session_store.py`
