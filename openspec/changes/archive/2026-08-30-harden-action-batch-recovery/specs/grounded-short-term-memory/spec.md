## MODIFIED Requirements

### Requirement: 事实摘要只暴露有效决策信息

系统 MUST 在每次 `think` 的任务上下文文本中追加受限事实摘要。摘要 MUST 过滤失效事实，限制事实数量、单条长度和总长度；MUST NOT 包含逻辑坐标、键盘输入正文、OCR 正文、历史截图定位编号、完整原始工具 JSON、已停用 `locate` 的标签或 `target_id`。历史持久化定位事实 MAY 被安全读取和裁剪，但 MUST NOT 回注模型上下文。

#### Scenario: 历史定位事实不进入上下文

- **WHEN** 恢复的任务上下文包含绑定当前截图的旧 `locate` 事实
- **THEN** 下一次模型请求的任务胶囊不包含其标签或 `target_id`

#### Scenario: 光标核验事实仍进入上下文

- **WHEN** 当前截图包含有效的光标核验事实
- **THEN** 下一次模型请求仍提示确认红十字后可调用无参数 `mouse_click`
