## ADDED Requirements

### Requirement: 默认 Agent 暴露语义 UI 工具

当存在当前有效 `UISnapshot` 时，默认工具 schema MUST 暴露与当前上下文兼容的语义 UI 动作，并使用 `element_id` 与 `ui_version` 作为唯一目标引用。默认 schema MUST NOT 暴露 BrowserBackend locator、AX 引用、DOM selector 或坐标作为结构化元素动作参数。无有效结构化快照时，系统 MUST 保留既有截图／OCR／视觉工具链。

#### Scenario: 浏览器快照暴露元素点击工具
- **WHEN** 当前有效快照的上下文为 `browser`
- **THEN** 模型可得到以 `element_id` 和 `ui_version` 为参数的语义点击 schema

#### Scenario: 无结构化快照保持视觉工具
- **WHEN** 当前任务不存在有效 `UISnapshot`
- **THEN** 默认工具集合仍提供既有截图和视觉后备工具，不伪造元素动作目标
