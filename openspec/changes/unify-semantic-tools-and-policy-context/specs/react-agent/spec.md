## ADDED Requirements

### Requirement: think 使用结构化单步 Policy 上下文
每次 `think` MUST 使用稳定的中文 Policy system 契约和当前任务的动态状态摘要。system MUST 要求模型只选择一个下一步、优先语义元素、优先活动模态、不得编造 element_id、不得原样重复失败动作，且只有当前可见证据支持时才调用 `task_complete`。动态摘要 MUST 依次提供任务、当前子任务、进度、环境、可见 UI、工作记忆、近期动作与上次结果；这些内容 MUST 与当前有效观察绑定，且不写入会话消息历史。

#### Scenario: 模态界面先于背景页面
- **WHEN** 当前桌面状态表明存在活动原生模态
- **THEN** 下一次 think 的 system 与动态摘要要求模型先处理模态，且可见 UI 不以背景浏览器元素为主

#### Scenario: Policy 上下文不持久化为会话消息
- **WHEN** 当前回合结束并保存会话
- **THEN** 会话消息中不包含 system 契约或完整动态状态摘要

### Requirement: 语义动作携带可验证 Policy 元数据
Agent MUST 从副作用语义工具调用中提取可选短 `intent` 和受限 `expectation`，在分派前将二者与工具实现参数隔离。`act` MUST 将 intent 以脱敏动作摘要传给状态层，`observe` MUST 以动作前后状态验证 expectation；工具成功本身不得推进 progress 或完成任务。expectation 不满足时，下一轮 think MUST 看到恢复提示与上次结果，并继续遵守既有恢复上限和阶段门禁。

#### Scenario: 工具实现不接收 intent
- **WHEN** 模型为 `click` 同时提交 element_id、ui_version、intent 和 expectation
- **THEN** click resolver 只接收元素引用，Agent 仍在观察阶段记录并验证 intent 与 expectation

#### Scenario: 完成声明不能替代验证
- **WHEN** 语义动作返回成功但其 expectation 尚未满足
- **THEN** Agent 不得将关联 progress 标为已验证，也不得仅据此以 task_complete 结束
