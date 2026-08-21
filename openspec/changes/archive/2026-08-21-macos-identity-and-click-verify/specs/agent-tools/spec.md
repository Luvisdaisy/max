## MODIFIED Requirements

### Requirement: 点击不带坐标

`mouse_click` MUST NOT 接受 `x`/`y` 或 `target_id`。若调用携带这些参数，MUST 返回中文错误并说明先使用 `mouse_move`，MUST NOT 移动指针，MUST NOT 点击。合法调用 MUST 只点击当前指针位置，且 MUST 满足桌面工具的光标验证（上次点击之后已 `mouse_move`，最近一帧为 `mouse_move` 或 `screenshot`）。

#### Scenario: 带坐标的点击被拒绝

- **WHEN** 模型调用 `mouse_click` 且参数含 `x`、`y`
- **THEN** 不点击，工具结果为错误，文案要求先 `mouse_move`

#### Scenario: 无坐标点击当前位置

- **WHEN** 最近一次成功工具为 `mouse_move`，模型调用无坐标的 `mouse_click`
- **THEN** 在当前指针位置单击
