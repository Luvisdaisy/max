## MODIFIED Requirements

### Requirement: 默认 Agent 暴露语义 UI 工具
当存在当前有效 `UISnapshot` 时，默认工具 schema MUST 暴露与当前主 UI 上下文兼容的轻量语义 UI 动作，并使用 `element_id` 与 `ui_version` 作为唯一目标引用。默认 schema MUST NOT 暴露 BrowserBackend locator、AX 引用、DOM selector、后端名称或坐标作为结构化元素动作参数。对于当前快照已覆盖的用户意图，默认 schema MUST 优先隐藏同意图的低层坐标动作；没有有效结构化快照、快照不含可用目标或主上下文为 vision 时，系统 MUST 保留既有截图／OCR／视觉工具链，且不伪造元素动作目标。`act` MUST 继续以产生当前模型回复时的允许工具集作二次门禁。

#### Scenario: 浏览器快照暴露元素点击工具
- **WHEN** 当前有效快照的上下文为 `browser`
- **THEN** 模型可得到以 `element_id` 和 `ui_version` 为参数的语义点击 schema，而不包含 locator 或坐标参数

#### Scenario: 无结构化快照保持视觉工具
- **WHEN** 当前任务不存在有效 `UISnapshot`
- **THEN** 默认工具集合仍提供既有截图和视觉后备工具，不伪造元素动作目标

#### Scenario: 语义覆盖时不暴露同意图坐标动作
- **WHEN** 当前快照包含可用的语义点击目标
- **THEN** schema 不同时把低层坐标点击作为该目标的等价首选路径暴露给模型
