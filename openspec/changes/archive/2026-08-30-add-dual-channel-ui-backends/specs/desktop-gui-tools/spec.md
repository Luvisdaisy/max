## ADDED Requirements

### Requirement: 坐标桌面工具作为视觉后备

当当前 UI 快照的元素 backend 为 `vision`，或结构化浏览器／AX 后端明确不可用且存在当前帧视觉目标时，系统 MUST 使用既有 `ViewFrame`、移鼠、光标截图与坐标换算规则执行坐标后备。Browser 或 AX 元素存在有效结构化 locator 时，系统 MUST NOT 因默认策略而改用坐标桌面工具。

#### Scenario: 结构化按钮不触发鼠标后备
- **WHEN** 当前有效元素为可点击的 `browser` 或 `macos_ax` 元素
- **THEN** 语义点击不调用 `mouse_move` 或 `mouse_click`

#### Scenario: 自绘界面使用视觉后备
- **WHEN** 当前界面没有可用 DOM／AX 元素，但视觉快照提供当前帧目标
- **THEN** 系统通过现有移鼠和截图核验链路执行坐标动作
