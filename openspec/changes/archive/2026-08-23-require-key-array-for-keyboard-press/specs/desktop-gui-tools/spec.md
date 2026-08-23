## MODIFIED Requirements

### Requirement: 输入文本与按键分离

`keyboard_type` MUST 只接受文本并写入当前前台窗口；MUST NOT 接受按键名。含非 ASCII 的文本 MUST 通过剪贴板粘贴，不得静默丢字。`keyboard_press.keys` MUST 只接受非空字符串数组；单键也必须使用单元素数组，例如 `["enter"]`，组合键必须使用数组，例如 `["command", "tab"]`。`keyboard_press` MUST NOT 接受自由文本、单个字符串或 JSON 数组文本形式的字符串。数组元素 MUST 是白名单键名；白名单外的键名 MUST 拒绝。关机或退出登录相关组合 MUST 拒绝。二者 MUST NOT 要求确认。本会话尚无成功的 `screenshot` 或 `mouse_move` 截图时，二者 MUST 拒绝执行并要求先截图或移鼠。

#### Scenario: 写入 ASCII 文本

- **WHEN** 已有光标截图，模型调用 `keyboard_type`，`text` 为 `1+1`
- **THEN** 该文本被输入到当前前台窗口，且不弹出确认

#### Scenario: 按下回车

- **WHEN** 已有光标截图，模型调用 `keyboard_press`，`keys` 为 `["enter"]`
- **THEN** 系统按下回车，且不把 `enter` 当作普通文本写入

#### Scenario: 按下组合键

- **WHEN** 已有光标截图，模型调用 `keyboard_press`，`keys` 为 `["command", "tab"]`
- **THEN** 系统将 `command` 与 `tab` 作为一个组合键发送

#### Scenario: 拒绝非数组格式

- **WHEN** 模型调用 `keyboard_press`，`keys` 为 `command+tab` 或 `["command", "tab"]` 的字符串表示
- **THEN** 工具返回要求使用非空字符串数组的错误，且不发送按键

#### Scenario: 拒绝未知键名

- **WHEN** 模型调用 `keyboard_press`，`keys` 含白名单外的名称
- **THEN** 工具返回错误且不发送按键

#### Scenario: 拒绝危险热键

- **WHEN** 模型调用 `keyboard_press`，`keys` 为 `["command", "q"]`
- **THEN** 工具返回错误且不发送按键

#### Scenario: 无截图则拒绝输入

- **WHEN** 本会话尚无成功截图，模型调用 `keyboard_type`
- **THEN** 不输入，工具结果为错误，文案要求先 `screenshot` 或 `mouse_move`
