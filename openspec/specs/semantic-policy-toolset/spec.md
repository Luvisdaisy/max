# semantic-policy-toolset Specification

## Purpose
TBD - created by archiving change unify-semantic-tools-and-policy-context. Update Purpose after archive.
## Requirements
### Requirement: 默认 Agent 使用轻量语义工具门面
存在当前有效 `UISnapshot` 时，系统 MUST 向默认 Agent 暴露与该快照上下文兼容的语义工具集合；集合 MUST 只使用任务意图级名称和 `element_id`／`ui_version` 等短期引用，MUST NOT 暴露 Playwright、AX、CGEvent、DOM selector、locator 或后端名称。工具实现 MUST 仍通过同一进程内的 `ToolRegistry` 分发到既有 BrowserBackend、MacOSAXBackend 或视觉后备。

#### Scenario: 浏览器元素使用统一点击
- **WHEN** 当前 browser UI 快照包含可点击元素
- **THEN** 模型得到 `click(element_id, ui_version)`，且不会得到 browser locator 或后端选择参数

#### Scenario: 原生弹窗覆盖浏览器
- **WHEN** 当前存在原生文件选择器并被选为主 UI 上下文
- **THEN** 模型只得到与 native 快照兼容的语义动作，不会同时得到后台网页的完整元素操作集合

### Requirement: 视觉后备保持显式且受限
当前没有有效语义 UI 快照、快照中不存在适合的目标或主上下文为 vision 时，系统 MUST 保留截图、OCR 与既有视觉桌面后备。视觉后备 MUST 继续满足当前帧、移鼠后置截图、无坐标点击及单次副作用门禁；有可操作语义目标时，系统 MUST NOT 为同一用户意图同时优先暴露低层坐标动作。

#### Scenario: 无结构化快照时使用视觉链路
- **WHEN** 当前截图有效但 browser 与 AX 都未生成 UI 快照
- **THEN** 模型可使用截图和既有视觉后备，且不能以历史元素编号调用语义点击

#### Scenario: 语义目标存在时隐藏同意图坐标动作
- **WHEN** 当前快照中存在可点击的语义目标
- **THEN** 模型优先只看到该语义点击路径，不能通过同一轮 schema 选择直接坐标点击绕开快照

### Requirement: 工具执行结果不推进任务状态
每个工具 MUST 返回带 `ok`、稳定 `code`、短中文 `text` 和可选脱敏 `data` 的 `ToolResult`；`data` 只能表达执行事实，例如已使用的动作类型、通道或当前元素引用。工具实现 MUST NOT 直接更新 `current_subtask`、progress、working memory、expectation 验证结果或任务完成状态。Agent MUST 在后置观察后独立更新这些状态。

#### Scenario: 语义点击只报告执行结果
- **WHEN** BrowserBackend 成功执行 `click`
- **THEN** ToolResult 表示调用成功和非敏感执行事实，但任务进度仍在后置观察前保持未验证

#### Scenario: 工具失败不伪造进度
- **WHEN** 任一后端返回错误或目标版本过期
- **THEN** ToolResult 返回 `ok=false` 和稳定 code，且不修改当前子任务或标记任务完成

