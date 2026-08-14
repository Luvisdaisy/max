## 1. 视图像素与截图摘要

- [x] 1.1 让 `prepare_image`（或抽出的共用缩放函数）返回编码后的实际宽高；更新所有调用方
- [x] 1.2 成功 `screenshot` 写入最近一次视图坐标系（原点、逻辑宽高、视图宽高），摘要增加 `view_width` / `view_height` / `origin`，`coordinate_space` 改为 `view`
- [x] 1.3 实现视图像素 → 逻辑像素换算与夹紧，供 `mouse_move` / `mouse_click` / `mouse_drag` 使用；无截图时回退逻辑像素并说明
- [x] 1.4 更新桌面工具描述：坐标是模型看见的图上的像素

## 2. 滚轮

- [x] 2.1 在 `DesktopBackend`、`PyAutoGUIBackend`、`FakeDesktopBackend` 增加 `scroll`
- [x] 2.2 实现 `mouse_scroll`（`clicks` 必填，可选视图 `x`/`y`），走桌面确认门并注册到默认表

## 3. 文字定位

- [x] 3.1 扩展 OCR 运行时与 transformers worker：可传入提示词与更大的 `max_new_tokens`；默认仍为 `OCR:`
- [x] 3.2 用夹具采样 `Spotting:` 输出并实现解析；解析失败返回中文错误
- [x] 3.3 实现 `ocr_locate`：路径规则与 `ocr` 相同、不确认、画编号框、返回 JSON + 带框图
- [x] 3.4 `mouse_click` / `mouse_move` 支持 `target_id`，命中最近一次 `ocr_locate` 的逻辑中心

## 4. 测试与文档

- [x] 4.1 单测：视图换算（含 region 与无截图回退）、`mouse_scroll` 确认门、`ocr_locate` 路径/解析/回退/画框、`target_id`
- [x] 4.2 运行 `uv run ruff format src tests` 与 `uv run ruff check src tests`
