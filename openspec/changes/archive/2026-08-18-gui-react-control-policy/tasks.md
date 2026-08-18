## 1. 系统提示与消息编码

- [x] 1.1 新增 GUI 中文 system 常量，并在 `to_chat_messages` 支持注入且不与已有 system 重复
- [x] 1.2 `think` 每次请求注入该 system；会话落盘与 TUI 记录不含 system
- [x] 1.3 `to_chat_messages` 全局只把最近两张仍存在的图编成 `image_url`，更早图改为路径与尺寸摘要

## 2. 计划状态与迭代上限

- [x] 2.1 `AgentState` 增加 `plan` / `current_subtask`；缺字段的旧检查点仍可恢复
- [x] 2.2 按设计规则从助手文本解析计划、改计划与子任务推进；工具失败不推进
- [x] 2.3 `max_iterations` 默认改为 20，环境变量仍可覆盖

## 3. 动作后观察

- [x] 3.1 `mouse_click` / `mouse_drag` / `mouse_scroll` / `keyboard_type` / `keyboard_press` 成功后在同一条 `ToolResult` 附新截图并更新坐标系
- [x] 3.2 取消、动作失败或后置截图黑图时不把空图发给模型；`mouse_move` / `screen_info` 不附截图

## 4. 会话内执行元数据与 TUI

- [x] 4.1 每次工具结果写入会话 tool 消息的 `name` 与嵌套 `exec`；不写 `artifacts/runs/`
- [x] 4.2 TUI 记录区只展示 tool 的 `text`；状态区不展示 `artifacts/runs/` 路径

## 5. 测试与规范

- [x] 5.1 补编码、system 注入、裁剪第三张图、计划解析、后置截图、会话 exec 与默认迭代的测试
- [x] 5.2 `uv run ruff format src tests` 与 `uv run ruff check src tests` 通过
