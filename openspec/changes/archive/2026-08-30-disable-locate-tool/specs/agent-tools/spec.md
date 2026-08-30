## MODIFIED Requirements

### Requirement: 统一工具协议

每个工具 MUST 暴露名称、JSON schema 与异步 invoke。`act` 节点 MUST 仅按名称分发已注册工具。未知工具名 MUST 返回工具错误消息，且 MUST NOT 把异常抛出图外。默认注册表 MUST NOT 包含 `read_file`、`write_file`、`list_dir`、`search_files` 或 `locate`。

#### Scenario: 已注册工具

- **WHEN** 模型调用已注册的 `screenshot`
- **THEN** `act` 分发该工具，`observe` 记录其结果

#### Scenario: 已禁用的 locate 按未知工具处理

- **WHEN** 模型调用 `locate`
- **THEN** `observe` 收到 `code=unknown_tool` 的结构化错误，且 MUST NOT 启动 OmniParser 或执行定位

#### Scenario: 未知工具名

- **WHEN** 模型调用 `not_a_tool`
- **THEN** `observe` 收到错误字符串，图继续进入 `think`

### Requirement: 默认注册桌面工具

默认工具注册表 MUST 包含 `screenshot`、`screen_info`、`mouse_move`、`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press`，且 MUST NOT 包含 `locate`。`act` MUST 仍按名称分发，未知名称行为不变。模型应使用最新截图中的视图像素坐标调用 `mouse_move`。

#### Scenario: 模型调用截图

- **WHEN** 模型调用已注册的 `screenshot`
- **THEN** `act` 分发该工具，`observe` 记录其结果

#### Scenario: schema 不暴露 locate

- **WHEN** Agent 导出默认工具 schema
- **THEN** schema 列表不含函数名 `locate`，但仍含 `screenshot` 与 `mouse_move`
