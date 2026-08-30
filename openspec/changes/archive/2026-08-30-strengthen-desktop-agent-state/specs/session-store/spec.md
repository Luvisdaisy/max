## ADDED Requirements

### Requirement: 持久化脱敏状态层
会话 JSON 的 `task_context` 与 checkpoint MUST 允许持久化经过清洗的桌面状态快照、进度、待验证预期和诊断结论。持久化对象 MUST 保留来源帧引用与必要短文本，但 MUST NOT 保存完整无障碍树、OCR／caption 正文、逻辑坐标、截图字节或键盘输入正文。旧会话缺少字段、字段类型错误或字段超过上限时 MUST 正常加载，并以空状态安全降级。

#### Scenario: 中断后恢复有效状态
- **WHEN** 同一任务中断，且 checkpoint 的状态快照与当前活动帧一致
- **THEN** 恢复后的任务可继续使用该快照、进度和待验证预期

#### Scenario: 旧会话兼容
- **WHEN** 会话 JSON 没有状态层字段或其中包含未知枚举值
- **THEN** SessionStore 正常加载会话，并将无效状态层字段视为空而不影响其他消息和 checkpoint
