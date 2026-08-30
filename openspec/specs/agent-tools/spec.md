# agent-tools Specification

## Purpose

统一 Function Calling 工具（图像、OCR、桌面）及结果回注。
## Requirements
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

### Requirement: 破坏性工具需确认

已注册工具 MUST NOT 因确认门而等待用户批准。`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press` 的 `confirmation_scope` MUST 为 `none`。会话 `auto_approve` 与 `auto_approve_desktop` MUST NOT 影响是否执行这些工具。

#### Scenario: 点击无需确认

- **WHEN** 模型在光标已由 `mouse_move` 验证后调用无坐标的 `mouse_click`
- **THEN** 不弹出确认并执行点击

### Requirement: 默认注册桌面工具

默认工具注册表 MUST 包含 `screenshot`、`screen_info`、`mouse_move`、`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press`，且 MUST NOT 包含 `locate`。`act` MUST 仍按名称分发，未知名称行为不变。模型应使用最新截图中的视图像素坐标调用 `mouse_move`。

#### Scenario: 模型调用截图

- **WHEN** 模型调用已注册的 `screenshot`
- **THEN** `act` 分发该工具，`observe` 记录其结果

#### Scenario: schema 不暴露 locate

- **WHEN** Agent 导出默认工具 schema
- **THEN** schema 列表不含函数名 `locate`，但仍含 `screenshot` 与 `mouse_move`

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

### Requirement: 工具结果可携带图像引用

工具 `invoke` MUST 允许返回纯文本，或返回带文本摘要与本地图像路径的结构化结果。`act` MUST 把图像路径写入对应 tool 消息，供后续 `think` 编码。

#### Scenario: 截图结果带图

- **WHEN** `screenshot` 成功并返回图像路径
- **THEN** 追加的 tool 消息同时包含文本摘要与该路径的图像引用

#### Scenario: 文本工具保持字符串

- **WHEN** `screen_info` 返回屏幕信息
- **THEN** tool 消息内容仍是文本，不含图像引用

### Requirement: 桌面破坏性工具使用独立确认

桌面点击、拖拽、滚动与键盘工具 MUST NOT 使用独立确认门，MUST 与其它工具一样立即执行（仍受光标验证与危险热键等既有安全规则约束）。

#### Scenario: 未开自动批准也直接按键

- **WHEN** 会话 `auto_approve` 与 `auto_approve_desktop` 均为假，且已有光标截图，模型调用 `keyboard_press`
- **THEN** 不弹确认并执行按键

### Requirement: 点击不带坐标

`mouse_click` MUST NOT 接受 `x`/`y` 或 `target_id`。若调用携带这些参数，MUST 返回中文错误并说明先使用 `mouse_move`，MUST NOT 移动指针，MUST NOT 点击。合法调用 MUST 只点击当前指针位置，且 MUST 满足桌面工具的光标验证（上次点击之后已 `mouse_move`，最近一帧为 `mouse_move` 或 `screenshot`）。

#### Scenario: 带坐标的点击被拒绝

- **WHEN** 模型调用 `mouse_click` 且参数含 `x`、`y`
- **THEN** 不点击，工具结果为错误，文案要求先 `mouse_move`

#### Scenario: 无坐标点击当前位置

- **WHEN** 最近一次成功工具为 `mouse_move`，模型调用无坐标的 `mouse_click`
- **THEN** 在当前指针位置单击

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

### Requirement: 默认 Agent 暴露语义 UI 工具

当存在当前有效 `UISnapshot` 时，默认工具 schema MUST 暴露与当前上下文兼容的语义 UI 动作，并使用 `element_id` 与 `ui_version` 作为唯一目标引用。默认 schema MUST NOT 暴露 BrowserBackend locator、AX 引用、DOM selector 或坐标作为结构化元素动作参数。无有效结构化快照时，系统 MUST 保留既有截图／OCR／视觉工具链。

#### Scenario: 浏览器快照暴露元素点击工具
- **WHEN** 当前有效快照的上下文为 `browser`
- **THEN** 模型可得到以 `element_id` 和 `ui_version` 为参数的语义点击 schema

#### Scenario: 无结构化快照保持视觉工具
- **WHEN** 当前任务不存在有效 `UISnapshot`
- **THEN** 默认工具集合仍提供既有截图和视觉后备工具，不伪造元素动作目标

