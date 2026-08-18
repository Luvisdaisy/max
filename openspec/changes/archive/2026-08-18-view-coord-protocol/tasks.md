## 1. 视图边界与摘要

- [x] 1.1 有视图帧且走 `x`/`y` 时，出界抛中文 `ToolError`（含坐标与视图宽高），不调用后端；`mouse_drag` 两端都校验
- [x] 1.2 `target_id` 与无截图路径保持现行为；换算后超出主屏仍夹紧
- [x] 1.3 成功摘要改为实际落点的视图像素，不写逻辑坐标数字；夹紧时说明
- [x] 1.4 补测试：视图外点击/拖拽拒绝；合法视图像素仍换算；无截图仍逻辑夹紧；`target_id` 不受视图边界限制

## 2. 系统契约

- [x] 2.1 更新 `GUI_SYSTEM_PROMPT`：视图宽高边界、禁止把逻辑坐标再当输入
- [x] 2.2 更新 `test_think_injects_system_not_persisted`（或等价用例）断言新约定

## 3. 收尾

- [x] 3.1 修正依赖逻辑坐标摘要的既有测试（如跨回合 `mouse_move`）
- [x] 3.2 `uv run ruff format src tests` 与 `uv run ruff check src tests`
- [x] 3.3 相关测试通过
