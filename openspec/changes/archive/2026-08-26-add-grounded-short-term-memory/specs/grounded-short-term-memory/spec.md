## ADDED Requirements

### Requirement: 任务内已落地事实记忆
系统 MUST 在当前任务的 `TaskContext` 中维护有上限的 `grounded_facts`，用于保存可复用且带来源的 GUI 事实。每条事实 MUST 至少包含种类、短标签、状态、来源截图标识与短结论；定位事实 MAY 包含 `target_id`，但 MUST NOT 保存逻辑桌面坐标、OCR 正文或 `keyboard_type` 输入正文。缺失、格式错误或超过上限的持久化事实 MUST 安全降级为空或被裁剪，MUST NOT 中断任务恢复。

#### Scenario: 定位生成最小事实
- **WHEN** 当前截图上的 `locate` 返回可执行的编号与标签
- **THEN** 当前任务保存绑定该截图的有效定位事实，模型摘要只需显示标签与 `target_id`

#### Scenario: 旧 checkpoint 缺少事实字段
- **WHEN** 恢复的 checkpoint 或会话 `task_context` 没有 `grounded_facts`
- **THEN** Agent 正常恢复，且事实记忆视为空

### Requirement: 事实摘要只暴露有效决策信息
系统 MUST 在每次 `think` 的任务上下文文本中追加受限事实摘要。摘要 MUST 过滤失效事实，限制事实数量、单条长度和总长度；MUST NOT 包含逻辑坐标、键盘输入正文、OCR 正文、历史截图定位编号或完整原始工具 JSON。

#### Scenario: 有效定位进入下一轮上下文
- **WHEN** 当前任务的完整工具调用链已被上下文裁剪，但仍有绑定当前截图的有效定位事实
- **THEN** 下一次模型请求仍包含该目标标签与 `target_id`

#### Scenario: 失效事实不进入上下文
- **WHEN** 一个定位事实的来源截图不再是当前视图帧
- **THEN** 下一次模型请求不包含该事实的标签或 `target_id`

### Requirement: 光标核验事实指导无坐标点击
成功使用有效定位编号完成 `mouse_move` 并得到后置截图后，系统 MUST 建立绑定后置截图的光标核验事实，说明已核验的目标标签和下一步可尝试无坐标 `mouse_click`。该事实 MUST 在后续破坏性桌面动作、失败或新的移动使其不再代表当前核验时失效；事实本身 MUST NOT 绕过既有点击门禁。

#### Scenario: 移动后避免重复定位
- **WHEN** Agent 已定位“Safari”、使用该编号完成 `mouse_move`，且后置截图成功
- **THEN** 下一次模型上下文提示已核验 Safari 且可根据该截图决定是否调用无参数 `mouse_click`，不再提示复用旧编号
