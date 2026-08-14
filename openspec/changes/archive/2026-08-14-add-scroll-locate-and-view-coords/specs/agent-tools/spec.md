## MODIFIED Requirements

### Requirement: 默认注册桌面工具

默认工具注册表 MUST 包含 `screenshot`、`screen_info`、`mouse_move`、`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press`。`act` MUST 仍按名称分发，未知名称行为不变。

#### Scenario: 模型调用截图

- **WHEN** 模型调用已注册的 `screenshot`
- **THEN** `act` 分发该工具，`observe` 记录其结果

### Requirement: 默认注册 OCR 工具

默认工具注册表 MUST 包含 `ocr` 与 `ocr_locate`。`act` MUST 仍按名称分发。`ocr` 与 `ocr_locate` MUST NOT 要求确认；会话普通自动批准与桌面自动批准都 MUST NOT 改变这一点。

#### Scenario: 模型调用 OCR

- **WHEN** 模型调用已注册的 `ocr` 且路径合法
- **THEN** `act` 分发该工具，`observe` 记录其结果，且不弹出确认

#### Scenario: 模型调用文字定位

- **WHEN** 模型调用已注册的 `ocr_locate` 且路径合法
- **THEN** `act` 分发该工具，`observe` 记录其结果，且不弹出确认

#### Scenario: 未知工具名行为不变

- **WHEN** 模型调用 `not_a_tool`
- **THEN** `observe` 仍收到未知工具错误，图继续进入 `think`

### Requirement: 桌面破坏性工具使用独立确认

`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press` MUST 等待用户明确批准，除非该会话开启了桌面自动批准。会话普通 `auto_approve` MUST NOT 跳过这些工具。被拒绝的调用 MUST 返回已取消结果，且 MUST NOT 执行。

#### Scenario: 普通自动批准不放行点击

- **WHEN** 会话 `auto_approve` 为真、`auto_approve_desktop` 为假，模型调用 `mouse_click`
- **THEN** TUI 仍弹出确认，在用户批准前不点击

#### Scenario: 桌面自动批准放行按键

- **WHEN** 会话 `auto_approve_desktop` 为真，模型调用 `keyboard_press`
- **THEN** 不弹确认并执行按键

#### Scenario: 普通自动批准不放行滚动

- **WHEN** 会话 `auto_approve` 为真、`auto_approve_desktop` 为假，模型调用 `mouse_scroll`
- **THEN** TUI 仍弹出确认，在用户批准前不滚动
