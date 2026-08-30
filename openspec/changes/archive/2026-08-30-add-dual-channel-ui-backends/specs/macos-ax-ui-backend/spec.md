## ADDED Requirements

### Requirement: macOS 原生 UI 的受限 AX 观察

在 macOS 且辅助功能 API 可用时，系统 MUST 从前台应用及其活动窗口读取有限的可交互 AX 元素。元素 MUST 映射为通用角色、短标签、可见／可用／可编辑／焦点状态和边界摘要；完整 AX 树、AXValue 正文和原始 AX 引用 MUST NOT 写入模型上下文或会话。权限不足、平台不支持或读取失败时 MUST 返回明确状态而非猜测。

#### Scenario: 前台原生窗口得到有限元素
- **WHEN** macOS 前台应用包含可访问的按钮和文本框
- **THEN** 系统生成仅含有限语义字段的 native UI 快照

#### Scenario: 辅助功能未授权
- **WHEN** 辅助功能信任检查失败
- **THEN** 系统标记 AX 通道不可用，并保留其他观察通道

### Requirement: AX 动作需要前台与版本匹配

系统执行 AX 动作前 MUST 校验元素所属 pid、前台应用／窗口身份和 `UISnapshot` 版本仍与当前观察匹配。按钮类控件 MUST 优先 `AXPress`；可编辑控件仅在支持且目标安全时使用 `AXValue`。不匹配、元素失效或不支持时 MUST 不执行 AX 动作，并返回稳定诊断。

#### Scenario: 按钮使用 AXPress
- **WHEN** 当前 native 快照中的按钮支持 `AXPress` 且前台身份匹配
- **THEN** 系统调用 `AXPress`，随后创建后置观察

#### Scenario: 前台窗口在动作前变化
- **WHEN** AX 元素的快照版本有效但前台窗口身份已变化
- **THEN** 系统拒绝动作并要求重新观察，且不得对旧元素执行 AX 操作

### Requirement: 原生文件选择器优先于浏览器内容

当浏览器或系统原生文件选择器、权限弹窗等模态窗口存在时，系统 MUST 选择 native UI 快照而非网页 DOM 快照；模态窗口消失后的新观察 MUST 作废 native 元素并重新选择可用通道。

#### Scenario: 网页点击后出现文件选择器
- **WHEN** 浏览器网页动作后观察到 macOS 文件选择器
- **THEN** 下一轮只向模型提供 native UI 元素，直到该对话框关闭
