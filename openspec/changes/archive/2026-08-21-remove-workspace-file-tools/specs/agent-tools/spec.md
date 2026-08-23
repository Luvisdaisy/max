## MODIFIED Requirements

### Requirement: 统一工具协议

每个工具 MUST 暴露名称、JSON schema 与异步 invoke。`act` 节点 MUST 仅按名称分发已注册工具。未知工具名 MUST 返回工具错误消息，且 MUST NOT 把异常抛出图外。默认注册表 MUST NOT 包含 `read_file`、`write_file`、`list_dir`、`search_files`。

#### Scenario: 已注册工具

- **WHEN** 模型调用已注册的 `screenshot`
- **THEN** `act` 分发该工具，`observe` 记录其结果

#### Scenario: 未知工具名

- **WHEN** 模型调用 `not_a_tool`
- **THEN** `observe` 收到错误字符串，图继续进入 `think`

#### Scenario: 已移除的文件工具按未知处理

- **WHEN** 模型调用 `read_file`、`write_file`、`list_dir` 或 `search_files`
- **THEN** `observe` 收到未知工具错误，且 MUST NOT 读写或搜索工作区文件

### Requirement: 破坏性工具需确认

已注册工具 MUST NOT 因确认门而等待用户批准。`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press` 的 `confirmation_scope` MUST 为 `none`。会话 `auto_approve` 与 `auto_approve_desktop` MUST NOT 影响是否执行这些工具。

#### Scenario: 点击无需确认

- **WHEN** 模型在光标已由 `mouse_move` 验证后调用无坐标的 `mouse_click`
- **THEN** 不弹出确认并执行点击

### Requirement: 工具结果可携带图像引用

工具 `invoke` MUST 允许返回纯文本，或返回带文本摘要与本地图像路径的结构化结果。`act` MUST 把图像路径写入对应 tool 消息，供后续 `think` 编码。

#### Scenario: 截图结果带图

- **WHEN** `screenshot` 成功并返回图像路径
- **THEN** 追加的 tool 消息同时包含文本摘要与该路径的图像引用

#### Scenario: 文本工具保持字符串

- **WHEN** `screen_info` 返回屏幕信息
- **THEN** tool 消息内容仍是文本，不含图像引用

## REMOVED Requirements

### Requirement: 限定工作区的文件系统工具

**Reason**：GUI Agent 主路径是键鼠操作屏幕，工作区读写不是必要能力，且与系统契约冲突。

**Migration**：不要再调用 `read_file` / `write_file` / `list_dir`。需要改本机文件时用桌面工具操作 Finder 或编辑器。旧会话里的历史 tool 消息可只读保留。

### Requirement: 本地文件搜索

**Reason**：本地内容搜索同属 coding agent 残留，不是 GUI 操作所需。

**Migration**：不要再调用 `search_files`。需要在屏幕上查找内容时用截图与 OCR。旧会话里的历史 tool 消息可只读保留。
