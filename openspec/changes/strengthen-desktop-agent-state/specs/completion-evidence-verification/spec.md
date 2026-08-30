## ADDED Requirements

### Requirement: 完成核验与进度终态一致
待验证进度或一般动作预期 MUST NOT 替代 `task_complete` 的独立后置观察要求。只有完成声明的现有独立校验通过后，系统才可把整个任务状态标为完成；此时系统 MUST 将仍未验证的必经进度项作为校验失败原因，而不得把它们自动标为已验证。

#### Scenario: 局部预期通过但任务未完成
- **WHEN** 一个局部进度项已通过 `element_appears` 验证，但模型尚未完成任务声明或独立完成校验
- **THEN** Agent 继续任务，不得将会话状态设为 `done`
