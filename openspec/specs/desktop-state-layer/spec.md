# desktop-state-layer Specification

## Purpose
TBD - created by archiving change strengthen-desktop-agent-state. Update Purpose after archive.
## Requirements
### Requirement: 当前帧桌面状态快照
系统 MUST 在成功创建当前可执行观察帧后维护一个 `desktop_snapshot`。快照 MUST 包含来源帧引用和采集时刻；可选包含前台应用、前台窗口、焦点元素、活动对话框和有限 UI 候选。前台应用、窗口、焦点和对话框无法可信采集时 MUST 明确表示为未知，MUST NOT 由模型文本、OCR 或视觉标签伪造。快照中的 UI 候选 MUST 绑定来源帧，且不得含逻辑坐标或可直接执行的操作句柄。

#### Scenario: 成功观察生成快照
- **WHEN** 系统成功获取一张可执行的当前截图并完成桌面状态采集
- **THEN** 任务上下文保存绑定该截图的快照，并将已知与未知字段分别明确表示

#### Scenario: 采集权限缺失
- **WHEN** 主机不支持前台身份采集或辅助功能权限不足
- **THEN** 系统保留截图与已有桌面工具能力，将受影响状态字段标为未知并保存机器可读诊断

### Requirement: 结构化 UI 候选的时效与边界
系统 MUST 只将当前帧上唯一可信的语义定位、OCR 或只读辅助功能观察归一为有限 UI 候选。新截图、桌面副作用后的后置截图、任务边界或恢复到不同帧时，系统 MUST 使旧快照 UI 候选、焦点和对话框状态失效。UI 候选 MUST NOT 放宽既有坐标、定位编号、移鼠或点击门禁。

#### Scenario: 新帧清除旧候选
- **WHEN** 当前帧存在 UI 候选，随后系统成功创建另一张截图
- **THEN** 新快照不继承旧候选、焦点或对话框，旧候选不得用于后续动作判断

#### Scenario: 模糊语义结果不成为候选
- **WHEN** 定位或读取结果包含多个同名候选、空标签或低可信度结果
- **THEN** 系统不得把该结果写入结构化 UI 候选

### Requirement: 预期驱动的任务进度
系统 MUST 维护有界 `progress` 项和可选 `current_expectation`。进度项 MUST 含稳定标识、短描述和状态；状态只能为 `pending`、`in_progress`、`verified` 或 `blocked`。预期 MUST 仅使用受限类型：`dialog_appears`、`active_window_changes`、`element_appears`、`element_disappears`、`element_selected` 或 `screen_changed`，并绑定创建它的当前帧和关联进度项。

成功桌面副作用后的后置观察 MUST 评估待验证预期。只有预期被观察证据确认时，系统才可将关联进度项推进为 `verified`；工具成功但预期未确认或无法确认时，进度 MUST 保持原状态，并记录中文原因和可恢复诊断。

#### Scenario: 弹窗出现推进进度
- **WHEN** 当前动作的预期为 `dialog_appears(file_picker)`，后置快照可信地报告文件选择对话框
- **THEN** 系统把关联进度项标为 `verified` 并清除该预期

#### Scenario: 工具成功但证据不足
- **WHEN** 一次点击返回成功，但后置快照无法确认关联预期
- **THEN** 系统不得推进进度，预期结论为未验证且模型上下文包含中文原因

### Requirement: 状态摘要与安全恢复
系统 MUST 向模型提供脱敏状态摘要，至少涵盖当前前台状态、当前子任务与进度、近期动作、当前帧有效的 UI 候选／短期事实和待验证预期。摘要 MUST NOT 包含逻辑坐标、键盘输入正文、完整 OCR 正文、历史帧候选或可执行定位编号。新用户任务 MUST 不继承上一任务的快照、进度、预期或 UI 候选；同一任务的中断恢复仅可恢复与活动帧一致且格式有效的状态。

#### Scenario: 新任务不继承桌面状态
- **WHEN** 同一会话开始一项新的用户任务
- **THEN** 新任务的快照、进度、预期和 UI 候选为空，历史观察仍仅按既有规则用于理解

#### Scenario: 恢复时丢弃过期状态
- **WHEN** checkpoint 中的快照来源不是恢复后的活动帧或字段格式无效
- **THEN** 系统丢弃该快照关联状态并继续恢复，不得中断任务或复用旧状态

