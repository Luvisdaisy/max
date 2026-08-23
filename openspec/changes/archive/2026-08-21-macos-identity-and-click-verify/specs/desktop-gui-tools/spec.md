## MODIFIED Requirements

### Requirement: 点击与拖拽需确认

`mouse_click` MUST 支持左/右/中键与单击/双击，MUST 只点击当前指针，MUST NOT 要求确认。`mouse_drag` MUST 从当前指针拖到视图像素 `(x2, y2)`，MUST NOT 要求确认。二者 MUST 要求本会话在上次点击/拖拽之后已经成功 `mouse_move` 放过光标，且最近一次光标截图来自 `mouse_move` 或其后的 `screenshot`。从未 `mouse_move`、或点击之后尚未再次 `mouse_move` 时 MUST 拒绝，并要求先移鼠看图。

#### Scenario: 当前位置单击

- **WHEN** 最近一次成功工具为 `mouse_move`，模型调用无坐标的 `mouse_click`
- **THEN** 在当前指针位置单击左键，不弹出确认

#### Scenario: move 后再截图仍可点击

- **WHEN** 模型先成功 `mouse_move`，再成功 `screenshot`，然后调用无坐标的 `mouse_click`
- **THEN** 在当前指针位置单击，MUST NOT 因最近一帧是 `screenshot` 而拒绝

#### Scenario: 未先移鼠则拒绝拖拽

- **WHEN** 本会话尚未成功 `mouse_move`，模型调用 `mouse_drag`
- **THEN** 不移动指针、不按下鼠标，工具结果为错误，文案要求先 `mouse_move`

## ADDED Requirements

### Requirement: macOS 拒绝 windows 键

当运行平台为 macOS 时，`keyboard_press` 的 `keys` 若含 `windows` 或 `win`，MUST 返回中文错误，说明本机是 macOS、应使用 `command`，MUST NOT 发送按键。其他平台 MUST NOT 仅因键名为 `windows` 而套用本条。

#### Scenario: macOS 上拒绝 Win+R

- **WHEN** 运行在 macOS，已有截图，模型调用 `keyboard_press`，`keys` 为 `["windows", "r"]`
- **THEN** 不按键，工具结果含「macOS」与「command」
