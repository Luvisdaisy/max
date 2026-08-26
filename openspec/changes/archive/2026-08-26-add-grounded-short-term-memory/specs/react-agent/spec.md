## ADDED Requirements

### Requirement: 系统契约引导复用当前帧定位
每次 `think` 的 GUI 系统契约 MUST 明确：当前截图存在有效定位事实时，模型 MUST 优先使用其中的 `target_id` 调用 `mouse_move`，MUST NOT 因同一定位目标重复调用 `locate`；当前帧没有有效定位时才调用 `locate`。移动后模型 MUST 依据后置截图的光标核验决定是否调用无坐标 `mouse_click`。

#### Scenario: 有有效定位时提示复用编号
- **WHEN** 当前任务上下文有绑定当前帧的有效定位事实
- **THEN** 模型请求的 system 或任务上下文明确该编号可用于 `mouse_move`

#### Scenario: 无有效定位时仍要求先定位
- **WHEN** 当前任务没有有效定位事实且需要点击图标或按钮
- **THEN** 系统契约仍要求先调用 `locate` 或以最近截图的视图像素移动光标，不允许猜测旧编号
