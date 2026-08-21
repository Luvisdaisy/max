## MODIFIED Requirements

### Requirement: 破坏性工具需确认

已注册工具 MUST NOT 因确认门而等待用户批准。`write_file`、`mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press` 的 `confirmation_scope` MUST 为 `none`。会话 `auto_approve` 与 `auto_approve_desktop` MUST NOT 影响是否执行这些工具。

#### Scenario: 写文件无需确认

- **WHEN** 模型调用 `write_file` 且路径合法
- **THEN** 不弹出确认，文件被写入工作区内部

#### Scenario: 点击无需确认

- **WHEN** 模型在光标已由 `mouse_move` 验证后调用无坐标的 `mouse_click`
- **THEN** 不弹出确认并执行点击

### Requirement: 桌面破坏性工具使用独立确认

桌面点击、拖拽、滚动与键盘工具 MUST NOT 使用独立确认门，MUST 与其它工具一样立即执行（仍受光标验证与危险热键等既有安全规则约束）。

#### Scenario: 未开自动批准也直接按键

- **WHEN** 会话 `auto_approve` 与 `auto_approve_desktop` 均为假，且已有光标截图，模型调用 `keyboard_press`
- **THEN** 不弹确认并执行按键

## ADDED Requirements

### Requirement: 点击不带坐标

`mouse_click` MUST NOT 接受 `x`/`y` 或 `target_id`。若调用携带这些参数，MUST 返回中文错误并说明先使用 `mouse_move`，MUST NOT 移动指针，MUST NOT 点击。合法调用 MUST 只点击当前指针位置。

#### Scenario: 带坐标的点击被拒绝

- **WHEN** 模型调用 `mouse_click` 且参数含 `x`、`y`
- **THEN** 不点击，工具结果为错误，文案要求先 `mouse_move`

#### Scenario: 无坐标点击当前位置

- **WHEN** 最近一次成功工具为 `mouse_move`，模型调用无坐标的 `mouse_click`
- **THEN** 在当前指针位置单击
