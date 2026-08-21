# agent-tools Specification

## Purpose

统一 Function Calling 工具（文件、搜索、图像、OCR、桌面）及结果回注。

## Requirements

### Requirement: 统一工具协议

每个工具 MUST 暴露名称、JSON schema 与异步 invoke。`act` 节点 MUST 仅按名称分发已注册工具。未知工具名 MUST 返回工具错误消息，且 MUST NOT 把异常抛出图外。

#### Scenario: 已注册工具

- **WHEN** 模型以合法路径调用 `read_file`
- **THEN** `act` 调用 `read_file`，`observe` 记录其结果

#### Scenario: 未知工具名

- **WHEN** 模型调用 `not_a_tool`
- **THEN** `observe` 收到错误字符串，图继续进入 `think`

### Requirement: 限定工作区的文件系统工具

`read_file`、`write_file`、`list_dir` MUST 将路径解析到已配置的工作区根之内。逃出工作区的路径 MUST 被拒绝。

#### Scenario: 读取工作区内文件

- **WHEN** 模型调用 `read_file`，参数为 `notes.md`，且该文件在工作区中存在
- **THEN** 工具返回文件内容

#### Scenario: 拒绝路径逃逸

- **WHEN** 模型调用 `read_file`，参数为 `../outside.txt`
- **THEN** 工具返回权限错误，且不读取该文件

### Requirement: 本地文件搜索

`search_files` MUST 在工作区下搜索文件内容，返回匹配路径与行摘录。MUST NOT 搜索工作区之外。

#### Scenario: 工作区内命中

- **WHEN** 模型调用 `search_files`，查询词出现在工作区某文件中
- **THEN** 结果包含该路径及匹配摘录

### Requirement: 破坏性工具需确认

已注册工具 MUST NOT 因确认门而等待用户批准。`write_file`、`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press` 的 `confirmation_scope` MUST 为 `none`。会话 `auto_approve` 与 `auto_approve_desktop` MUST NOT 影响是否执行这些工具。

#### Scenario: 写文件无需确认

- **WHEN** 模型调用 `write_file` 且路径合法
- **THEN** 不弹出确认，文件被写入工作区内部

#### Scenario: 点击无需确认

- **WHEN** 模型在光标已由 `mouse_move` 验证后调用无坐标的 `mouse_click`
- **THEN** 不弹出确认并执行点击

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

### Requirement: 工具结果可携带图像引用

工具 `invoke` MUST 允许返回纯文本，或返回带文本摘要与本地图像路径的结构化结果。`act` MUST 把图像路径写入对应 tool 消息，供后续 `think` 编码。

#### Scenario: 截图结果带图

- **WHEN** `screenshot` 成功并返回图像路径
- **THEN** 追加的 tool 消息同时包含文本摘要与该路径的图像引用

#### Scenario: 文本工具保持字符串

- **WHEN** `read_file` 返回文件内容
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
