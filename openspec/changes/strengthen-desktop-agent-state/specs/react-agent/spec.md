## ADDED Requirements

### Requirement: ReAct 观察节点更新状态层
`observe` 节点 MUST 在每次成功观察后更新任务状态快照、最近动作结论、待验证预期和进度，并在下一次 `think` 前注入脱敏状态摘要。Agent MUST 将无法验证的预期作为恢复信息回传模型，MUST NOT 仅因为桌面工具未报错就推进计划或进度。现有 `plan` 与 `current_subtask` 仍可用，但不得与已验证进度冲突。

#### Scenario: 后置观察后更新模型上下文
- **WHEN** 一次桌面副作用完成并获得后置截图
- **THEN** 下一次 `think` 收到该截图绑定的状态摘要和预期结论

#### Scenario: 未验证预期阻止自动推进
- **WHEN** 当前进度项存在未验证预期
- **THEN** Agent 不得仅依据助手文本中的“子任务完成”或工具成功自动将该项标为已验证
