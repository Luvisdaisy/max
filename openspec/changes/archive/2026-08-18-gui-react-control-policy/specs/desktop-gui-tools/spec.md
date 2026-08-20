## ADDED Requirements

### Requirement: 变异动作成功后附新截图

`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press` 在桌面后端执行成功后，MUST 再截取当前画面，按既有 `screenshot` 规则落盘、更新视图坐标系，并把该 PNG 作为同一条工具结果的图像回注。结果文本 MUST 仍包含原动作摘要，且 MUST 包含新截图的路径与视图尺寸信息。用户取消、动作失败或权限错误时 MUST NOT 追加截图，MUST NOT 用空图或黑图更新坐标系。`mouse_move` 与 `screen_info` MUST NOT 因此附带截图。后置截图失败（全黑或过小）时 MUST 保留动作摘要与中文权限说明，MUST NOT 把该空图发给模型。

#### Scenario: 单击成功带回新图

- **WHEN** 用户批准 `mouse_click` 且后端点击成功
- **THEN** 该次工具结果含新 PNG 引用，摘要含新图路径，且会话视图坐标系更新为该图

#### Scenario: 拒绝点击不截图

- **WHEN** 模型调用 `mouse_click` 且用户拒绝
- **THEN** 不点击、不追加截图，工具结果为已取消

#### Scenario: 移动指针不附截图

- **WHEN** 模型调用 `mouse_move` 且移动成功
- **THEN** 工具结果不含新截图图像引用
