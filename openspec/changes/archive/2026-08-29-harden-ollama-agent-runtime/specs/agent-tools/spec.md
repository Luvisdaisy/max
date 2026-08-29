## ADDED Requirements

### Requirement: 工具声明副作用元数据

每个工具 MUST 声明是否产生真实环境副作用。`mouse_move`、`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type` 与 `keyboard_press` MUST 为副作用；截图、屏幕信息、图像、OCR、定位与 `task_complete` MUST 为非副作用。注册表 MUST 允许 Agent 按名称查询该元数据并按允许名称生成 schema。

#### Scenario: 查询点击元数据

- **WHEN** Agent 查询 `mouse_click` 的工具定义
- **THEN** 注册表报告它是副作用工具

#### Scenario: 按名称生成 schema

- **WHEN** 当前阶段只允许 `screenshot` 与 `screen_info`
- **THEN** 注册表生成的 schema 只含这两个名称

### Requirement: 工具参数严格校验

注册表 MUST 在调用实现之前，按工具 JSON Schema 校验参数类型、必填字段、枚举、数组最小长度和未知字段。所有对象 schema MUST 含 `additionalProperties=false`，包括嵌套对象。参数不是合法 JSON 对象或校验失败时 MUST 返回 `ok=false`、`code=invalid_arguments` 的结构化结果，MUST NOT 调用工具实现。

#### Scenario: 未知参数被拒绝

- **WHEN** 模型为 `mouse_click` 传入 schema 未声明的 `x`
- **THEN** 注册表返回 `invalid_arguments` 且桌面后端没有收到点击

#### Scenario: 键数组类型错误被拒绝

- **WHEN** 模型为 `keyboard_press.keys` 传入字符串而非非空字符串数组
- **THEN** 注册表返回 `invalid_arguments` 且键盘后端没有收到按键

### Requirement: 工具调用具有超时和结构化结果

注册表 MUST 对每次工具实现调用施加 `MAX_GUI_TOOL_TIMEOUT`。未知工具、阶段拒绝、参数错误、批次拒绝、超时、业务 `ToolError` 与未预期异常 MUST 返回带 `ok=false`、稳定 `code` 和中文 `text` 的 `ToolResult`；正常字符串或多模态结果 MUST 视为 `ok=true`。超时任务 MUST 被取消，MUST NOT 把异常抛出图外。

#### Scenario: 工具执行超时

- **WHEN** 工具实现超过配置的超时仍未返回
- **THEN** 注册表取消等待并返回 `code=timeout` 的结构化错误，Agent 继续进入观察

#### Scenario: 未知工具结构化失败

- **WHEN** 模型调用未注册工具
- **THEN** 注册表返回 `code=unknown_tool`、`ok=false`，且不抛出异常
