## ADDED Requirements

### Requirement: 语义定位仍受当前帧坐标边界约束

语义视觉定位和 macOS Dock 语义发现 MUST 仅在其候选边界可投影到当前活动 `ViewFrame` 时生成可执行编号。历史图、屏幕外元素、投影失败或观察专用图 MUST 标为仅观察并清空可执行定位表。

#### Scenario: 历史观察查询 Chrome 仅供描述
- **WHEN** 模型对会话级历史截图执行 Chrome 查询而该图不是当前活动帧
- **THEN** 返回结果仅供观察，不产生可供 `mouse_move` 使用的编号
