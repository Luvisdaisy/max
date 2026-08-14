## ADDED Requirements

### Requirement: 桌面工具确认不受普通自动批准影响

TUI 确认门 MUST 按工具类别区分：工作区破坏性工具可读会话 `auto_approve`；桌面破坏性工具只读 `auto_approve_desktop`。未开启对应开关时，MUST 弹出中文确认对话框。

#### Scenario: 批准写文件后仍确认点击

- **WHEN** 当前会话已开启普通自动批准，Agent 请求 `mouse_click`
- **THEN** TUI 弹出是否允许执行 `mouse_click` 的确认框

#### Scenario: 用户拒绝桌面动作

- **WHEN** TUI 展示桌面工具确认且用户选择拒绝
- **THEN** 该动作不执行，记录区可见已取消结果

### Requirement: 展示桌面权限错误

当桌面工具返回屏幕录制或辅助功能失败时，TUI MUST 在记录区展示工具给出的中文步骤，且 MUST NOT 崩溃。

#### Scenario: 记录区显示授权步骤

- **WHEN** `screenshot` 因屏幕录制未授权失败
- **THEN** 记录区显示中文授权步骤
