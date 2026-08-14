## ADDED Requirements

### Requirement: 默认注册 OCR 工具

默认工具注册表 MUST 包含 `ocr`。`act` MUST 仍按名称分发。`ocr` MUST NOT 要求确认；会话普通自动批准与桌面自动批准都 MUST NOT 改变这一点。

#### Scenario: 模型调用 OCR

- **WHEN** 模型调用已注册的 `ocr` 且路径合法
- **THEN** `act` 分发该工具，`observe` 记录其结果，且不弹出确认

#### Scenario: 未知工具名行为不变

- **WHEN** 模型调用 `not_a_tool`
- **THEN** `observe` 仍收到未知工具错误，图继续进入 `think`
