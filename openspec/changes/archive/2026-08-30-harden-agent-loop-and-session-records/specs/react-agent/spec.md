## MODIFIED Requirements

### Requirement: ReAct 状态机
Agent SHALL 用 LangGraph StateGraph 实现 `think`、`act`、`observe` 节点。一个回合 MUST 从 `think` 开始。若模型返回工具调用，图 MUST 先跑 `act` 再 `observe`。普通工具观察后 MUST 回到 `think`；仅当独立完成证据校验通过后才 MUST 从 `observe` 结束。纯对话或只读观察任务中，模型不再返回工具调用时图 MUST 以 `done` 结束。任务已经成功执行副作用但尚未通过完成声明与独立校验时，模型不返回工具调用 MUST NOT 直接结束；图 MUST 保留正文、标记仍需完成验证并再次进入 `think`，且该重试计入迭代上限。恢复护栏耗尽时图 MUST 以 `error` 结束。

#### Scenario: 纯文本完成
- **WHEN** 模型返回最终助手消息且当前任务未执行副作用
- **THEN** 图状态为 `done`，且不调用任何工具

#### Scenario: 一次工具循环
- **WHEN** 模型返回普通工具调用且工具成功
- **THEN** 图执行 `act` 再 `observe`，追加工具结果，并再次调用 `think`

#### Scenario: 副作用后正文不能直接完成
- **WHEN** 最近成功副作用已经回注截图，但模型只返回正文且没有调用完成声明工具
- **THEN** 图不标记 `done`，任务胶囊提示仍需完成验证并再次调用 `think`

#### Scenario: 完成声明通过后结束
- **WHEN** 模型在成功副作用的后置截图之后调用 `task_complete` 且参数有效，并且声明后的独立观察校验通过
- **THEN** 图经过 `act`、声明后观察与校验后以 `done` 结束，不再额外调用模型

#### Scenario: 完成校验失败继续
- **WHEN** `task_complete` 的独立后置观察或证据校验失败
- **THEN** 图不得以 `done` 结束，而是向模型回注失败原因并回到 `think`
