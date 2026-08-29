## ADDED Requirements

### Requirement: 语义定位候选复用既有移动核验

来自语义视觉定位或 macOS Dock 发现的候选 MUST 仅在绑定当前活动 `ViewFrame` 时写入定位表。`mouse_move` 使用该编号后 MUST 继续回注光标截图；语义名称不得替代移动、后置截图或无坐标点击门禁。

#### Scenario: Chrome 语义候选移动后仍核验
- **WHEN** 当前帧中的 Chrome 语义候选被用于 `mouse_move(target_id=...)`
- **THEN** 系统移动鼠标并返回含光标的新截图，尚未自动点击 Chrome
