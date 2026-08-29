## ADDED Requirements

### Requirement: 持久化会话级只读视觉上下文

会话 JSON MUST 允许持久化会话级只读视觉上下文。该字段与 `task_context` 分离，缺失、格式错误或引用图像不存在时 MUST 安全降级，且不得改变会话消息恢复、自动批准或当前运行模型选择行为。

#### Scenario: 旧会话兼容
- **WHEN** 加载的会话 JSON 不含会话级只读视觉上下文字段
- **THEN** 会话正常加载并把该上下文视为空
