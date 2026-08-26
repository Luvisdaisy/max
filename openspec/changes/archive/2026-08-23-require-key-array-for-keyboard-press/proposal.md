## Why

`keyboard_press` 的工具说明曾同时允许字符串与数组，但模型在调用组合键时把数组再序列化为字符串，导致 `Command+Tab`、`Command+Space` 在校验阶段被拒绝，实际按键从未发出。组合键是切换应用等桌面流程的基础能力，需要消除这一歧义。

## What Changes

- **BREAKING**：`keyboard_press.keys` 仅接受非空字符串数组；不再接受单个字符串或以 JSON 数组文本表示的字符串。
- 更新工具说明，明确组合键必须使用 JSON 字符串数组，示例为 `["command", "tab"]`。
- 保持既有白名单、危险热键和 macOS `windows` 键保护，并新增组合键及错误格式的回归测试。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `desktop-gui-tools`：将 `keyboard_press` 的键参数收紧为唯一的字符串数组格式。

## Impact

- 修改 `src/max_gui/tools/desktop.py` 的参数 schema、解析与用户可见错误。
- 修改 `tests/test_tools.py` 的桌面按键用例。
- 不新增依赖，也不改变桌面后端调用方式。
