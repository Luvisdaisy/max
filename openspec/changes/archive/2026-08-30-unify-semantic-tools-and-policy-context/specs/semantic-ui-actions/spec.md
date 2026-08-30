## MODIFIED Requirements

### Requirement: 统一语义动作与后端分派
系统 MUST 向模型提供以元素为目标的 `click`、`double_click`、`type_text`、`press_key`、`press_shortcut`、`scroll`、`drag`、`activate_app`、`open_url`、`wait`、`set_file_input`、`select_option` 与 `task_complete`，并按当前主 UI 上下文选择最小兼容子集。Resolver MUST 依据当前元素的 backend 分派到 BrowserBackend、MacOSAXBackend 或受现有坐标门禁保护的 vision 后备；模型 MUST NOT 传递后端名称、坐标或私有 locator。每个语义工具的描述 MUST 说明适用条件与禁止用法，使模型可仅从 schema 判断何时使用该工具。

#### Scenario: 语义点击自动选择浏览器后端
- **WHEN** 模型对当前 `browser` 元素调用 `click`
- **THEN** Resolver 只调用 BrowserBackend 的点击实现

#### Scenario: vision 元素回退到既有坐标门禁
- **WHEN** 模型对当前 `vision` 元素调用 `click`
- **THEN** 系统先遵守现有移鼠与截图核验规则，再执行坐标点击

#### Scenario: 工具描述约束元素引用
- **WHEN** 模型读取 `click` 的 schema
- **THEN** 描述明确该工具只可用于当前 UI 快照中可见的 element_id，且不得用于输入文本
