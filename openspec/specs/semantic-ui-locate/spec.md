# semantic-ui-locate Specification

## Purpose
TBD - created by archiving change add-conversational-visual-context-and-semantic-locate. Update Purpose after archive.
## Requirements
### Requirement: 查询驱动的语义视觉定位

`locate` MUST 接受可选目标名称查询和可选区域限定。查询存在时，系统 MUST 只为当前活动截图中唯一且可信的语义匹配项提供可执行编号与目标名称；无匹配、标签泛化、caption 不可用或多个候选时 MUST 返回可诊断的未匹配 / 歧义结果，MUST NOT 把 `icon`、空标签或猜测名称作为匹配。

#### Scenario: 唯一 Chrome 候选
- **WHEN** 当前截图的 Dock 区域中唯一候选被可靠识别为 Chrome，模型调用带 Chrome 查询的 `locate`
- **THEN** 结果含 Chrome 标签和当前帧可用 `target_id`，后续可进入既有 `mouse_move` 核验链

#### Scenario: 多个同名候选
- **WHEN** 查询得到两个或更多同名且无法区分的候选
- **THEN** 结果标记歧义且不写入可执行定位表

### Requirement: macOS Dock 只读语义发现

系统 MUST 在 macOS 上支持只读发现 Dock 应用的标题、角色和边界，并在名称唯一匹配且落入当前活动截图时产生语义候选。该能力 MUST 检查辅助功能权限，MUST NOT 通过辅助功能 API 直接激活应用、点击图标或执行其它副作用。

#### Scenario: 辅助功能发现 Chrome
- **WHEN** 辅助功能权限可用，Dock 暴露唯一标题为 Chrome 的应用，且该边界位于当前活动截图内
- **THEN** 系统返回可供 `mouse_move` 使用的 Chrome 候选，并要求后置截图核验

#### Scenario: 权限不可用
- **WHEN** macOS 未授予辅助功能权限或 Dock 未提供可用元素
- **THEN** 系统返回中文可诊断状态，不移动鼠标、不执行辅助功能动作，并允许视觉定位回退

