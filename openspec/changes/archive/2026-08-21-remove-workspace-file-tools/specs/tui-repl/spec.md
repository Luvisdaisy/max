## MODIFIED Requirements

### Requirement: 工具执行不弹确认

TUI MUST NOT 因 Agent 调用 `mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type` 或 `keyboard_press` 而弹出确认对话框。工具结果仍写入记录区。

#### Scenario: 点击不弹框

- **WHEN** Agent 请求 `mouse_click`
- **THEN** 界面不出现「允许执行」对话框，记录区随后可见工具结果
