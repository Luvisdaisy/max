## REMOVED Requirements

### Requirement: 桌面工具确认不受普通自动批准影响

**Reason**：本变更取消全部工具确认，TUI 不再按 scope 弹框。

**Migration**：删除 `ConfirmScreen` 调用路径。会话 JSON 仍可读 `auto_approve` 字段，但不再用于放行或拦截工具。

## ADDED Requirements

### Requirement: 工具执行不弹确认

TUI MUST NOT 因 Agent 调用 `write_file`、`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type` 或 `keyboard_press` 而弹出确认对话框。工具结果仍写入记录区。

#### Scenario: 点击不弹框

- **WHEN** Agent 请求 `mouse_click`
- **THEN** 界面不出现「允许执行」对话框，记录区随后可见工具结果
