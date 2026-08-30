## ADDED Requirements

### Requirement: 帧绑定统一 UI 快照

系统 MUST 为每次有效 UI 观察创建一个 `UISnapshot`，含单调递增 `ui_version`、来源帧、`ui_context` 与有限 `UIElement` 集合。每个 `UIElement` MUST 标记为 `browser`、`macos_ax` 或 `vision` 后端，并仅在其快照版本内以短期 `element_id` 可解析。新截图、通道切换、原生副作用、恢复到不同帧或任务边界 MUST 作废旧元素。

#### Scenario: 新观察作废旧元素
- **WHEN** 当前 `ui_version=21` 的快照后生成新的有效观察
- **THEN** 新快照版本大于 21，且版本 21 的 `element_id` 不再可用于动作

#### Scenario: 旧版本目标被拒绝
- **WHEN** 模型以 `ui_version=21` 调用当前版本为 22 的元素动作
- **THEN** 系统返回稳定的过期 UI 错误，且不分派任何后端操作

### Requirement: 统一语义动作与后端分派

系统 MUST 向模型提供以元素为目标的 `click`、`double_click`、`type_text`、`press_key`、`press_shortcut`、`scroll`、`drag`、`activate_app`、`open_url`、`wait`、`set_file_input`、`select_option` 与 `task_complete`。Resolver MUST 依据当前元素的 backend 分派到 BrowserBackend、MacOSAXBackend 或受现有坐标门禁保护的 vision 后备；模型 MUST NOT 传递后端名称、坐标或私有 locator。

#### Scenario: 语义点击自动选择浏览器后端
- **WHEN** 模型对当前 `browser` 元素调用 `click`
- **THEN** Resolver 只调用 BrowserBackend 的点击实现

#### Scenario: vision 元素回退到既有坐标门禁
- **WHEN** 模型对当前 `vision` 元素调用 `click`
- **THEN** 系统先遵守现有移鼠与截图核验规则，再执行坐标点击

### Requirement: 语义动作不等同任务成功

任何产生副作用的语义动作 MUST 登记动作预期、限制单次工具批次中的副作用数量，并在后置观察后才能推进关联进度。语义后端返回成功 MUST NOT 跳过 `task_complete` 的独立完成证据校验。

#### Scenario: locator 点击后仍需完成证据
- **WHEN** 浏览器 locator 点击返回成功
- **THEN** Agent 进入后置观察；未通过完成声明和独立证据校验时任务不得结束
