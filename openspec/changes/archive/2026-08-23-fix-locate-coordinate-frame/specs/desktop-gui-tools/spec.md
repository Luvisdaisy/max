## ADDED Requirements

### Requirement: 桌面工具拒绝无当前坐标帧的定位编号

`mouse_move` 与支持 `target_id` 的 `mouse_scroll` MUST 只接受由当前会话当前截图坐标帧生成的定位编号。定位工具清空编号、当前截图刷新编号或会话中不存在有效编号时，桌面工具 MUST 返回中文错误，MUST NOT 移动、滚动或点击。该限制 MUST 不影响模型直接传入最近截图的视图像素坐标。

#### Scenario: 观察专用定位后拒绝编号

- **WHEN** 模型对非当前截图调用 `locate`，随后以返回的 `target_id` 调用 `mouse_move`
- **THEN** `mouse_move` 返回要求先对当前截图调用 `locate` 的中文错误，且桌面后端不接收移动操作
