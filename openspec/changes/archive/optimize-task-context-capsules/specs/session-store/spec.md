## ADDED Requirements

### Requirement: 持久化可选任务上下文快照
会话 JSON MUST 允许保存可选的任务上下文快照，以支持中断任务恢复和任务边界判断。快照 MUST 包含任务
标识、原始用户指令、状态、计划、当前子任务、最新观察引用及近期动作摘要；不得包含截图字节、base64、
完整 OCR 文本或 `keyboard_type` 输入正文。全量 `messages`、checkpoint、视图坐标系和定位表 MUST 继续
按原有语义保存。缺少该字段的旧会话和旧 checkpoint MUST 仍能加载。

#### Scenario: 中断任务快照可恢复
- **WHEN** 一个任务以 `interrupted` 状态保存
- **THEN** 会话 JSON 同时保留现有 checkpoint 与该任务的上下文快照

#### Scenario: 旧会话兼容加载
- **WHEN** 既有会话 JSON 不含任务上下文快照
- **THEN** store 成功加载该会话，并将其视为没有可直接续接的新格式任务
