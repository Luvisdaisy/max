## MODIFIED Requirements

### Requirement: 破坏性工具需确认

`write_file` MUST 等待用户在 TUI 中明确批准，除非该会话已开启自动批准。被拒绝的调用 MUST 返回已取消结果，且 MUST NOT 执行。会话自动批准 MUST NOT 批准桌面破坏性工具。

#### Scenario: 用户批准写入

- **WHEN** 模型调用 `write_file` 且用户确认
- **THEN** 文件被写入工作区内部

#### Scenario: 用户拒绝写入

- **WHEN** 模型调用 `write_file` 且用户拒绝
- **THEN** 文件不写入，工具结果为已取消

#### Scenario: 工作区自动批准不覆盖桌面

- **WHEN** 会话已开启自动批准，模型调用 `write_file` 与 `mouse_click`
- **THEN** `write_file` 无需再确认，`mouse_click` 仍需确认

## REMOVED Requirements

### Requirement: 沙箱 Python 执行

**Reason**：GUI Agent 不再提供任意代码执行；该工具不是主路径，且单独扩大攻击面。

**Migration**：不要再调用 `run_python`。需要处理工作区文件时使用 `read_file` / `write_file` / `list_dir` / `search_files`。需要桌面操作时使用桌面工具。旧会话里的历史 tool 消息可只读保留。

### Requirement: 禁止经 Python 沙箱控制桌面

**Reason**：`run_python` 已删除，不再存在经沙箱导入桌面控制库的路径。

**Migration**：桌面操作只走已注册的桌面工具及其确认门。无需再维护 AST 拦截。
