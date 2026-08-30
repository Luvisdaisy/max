## MODIFIED Requirements

### Requirement: GUI 系统契约注入

每次 `think` 发给模型的消息列表 MUST 以一条中文 `role=system` 消息开头。该消息 MUST 要求：桌面任务一律用键鼠完成；每一次键鼠动作都必须截图核验；还没有画面时先 `screenshot`；要点、拖、输入前先 `mouse_move`，根据回注图上的光标判断位置，对了再调用不带坐标的 `mouse_click` 或拖拽/键盘；看到回注图后 MUST 先判断红十字落在哪个控件上，与目标不一致则再 `mouse_move`，MUST NOT 在未看图时点击；坐标只用最近一帧视图像素，且视图像素必须落在该帧 `view_width`×`view_height` 内；不要用逻辑分辨率、屏幕百分比或归一化坐标，也不要把工具摘要里的逻辑坐标再当输入；看不清字再调用 `ocr`；破坏性桌面动作一次一个，并在每次工具回复中至多提交一个；动作后根据新画面判断是否进入下一子任务；首轮尽量输出编号子任务。该消息与默认模型可见工具 schema MUST NOT 提及或推荐已停用的 `locate`、`target_id` 或定位编号。该消息 MUST 写明当前操作系统的中文名称；当主机为 macOS 时 MUST 写明不是 Windows，快捷键用 `command` 而不是 `windows`。若当前会话已有视图帧，该消息 MUST 包含该帧的 `view_width` 与 `view_height`。该 `system` 消息 MUST NOT 写入会话 JSON，MUST NOT 作为 TUI 记录区条目出现。

#### Scenario: think 请求不含停用定位路径

- **WHEN** Agent 进入 `think` 并调用推理客户端
- **THEN** system 正文和默认模型可见工具 schema 包含截图、视图像素、单个副作用与核验约束，且不含 `locate`、`target_id` 或 `ocr_locate`

### Requirement: 同一观察最多执行一个副作用工具

每次 `think` 返回的调用批次 MUST 按原顺序处理。系统 MAY 执行第一个副作用之前的只读调用和第一个副作用；第一个副作用之后的所有调用 MUST 返回 `action_batch_blocked`，MUST NOT 调用其实现。所有原始 `tool_call_id` MUST 取得一条配对 tool 消息。`mouse_move` MUST 视为副作用。阻断错误 MUST 明确要求模型在下一次回复只提交一个副作用调用，并先观察该动作后的截图。

#### Scenario: 两个副作用只执行第一个

- **WHEN** 同一模型回复依次调用 `mouse_move` 与 `mouse_click`
- **THEN** 系统执行 `mouse_move`，拒绝 `mouse_click`，两次调用都有配对 tool 消息，并在错误中要求先阅读移动后的截图

### Requirement: 批次阻断进入恢复护栏

一次 `observe` 中只要存在 `action_batch_blocked`，系统 MUST 按该批次记录一次稳定的恢复失败，并向下一次 `think` 回注“只提交一个副作用、先观察后置截图”的恢复提示；同一批次内任意数量的被阻断调用 MUST NOT 多次增加恢复计数。相同批次违规在同一活动截图上连续达到既有恢复阈值时，Agent MUST 以 `recovery_exhausted` 结束。成功 `screenshot` MUST 清除该恢复状态。

#### Scenario: 单批次多个阻断调用只计一次

- **WHEN** 一个模型回复的首个副作用后还有多个调用，且它们都返回 `action_batch_blocked`
- **THEN** 本次观察仅将恢复失败计数增加一次

#### Scenario: 重复批次有界终止

- **WHEN** 模型在同一活动截图上连续两次回复包含多个副作用调用
- **THEN** 第二次观察后 Agent 状态为 `error`，错误与终止原因为 `recovery_exhausted`

#### Scenario: 重新截图解除护栏

- **WHEN** 批次阻断后模型先成功调用 `screenshot`
- **THEN** 恢复失败计数清零，下一次可按单个副作用协议继续执行
