## MODIFIED Requirements

### Requirement: think 推理异常结束为 error

`think` 调用推理客户端失败时，客户端 MUST 先按推理重试策略处理可重试错误。每次网络重试 MUST 保持在同一次 `think` 和同一 ReAct iteration 内，MUST NOT 重新执行已经成功的工具。仅当错误不可重试、流已产生有效增量后失败、用户中断或重试耗尽时，控制权才返回 Agent。最终推理失败时 Agent MUST 将图状态设为 `error`，写入人类可读错误，MUST NOT 把未捕获异常甩出图外导致会话仍为上一回合的 `done`；用户中断仍按既有中断语义处理。

#### Scenario: 瞬时错误重试成功

- **WHEN** `/chat/completions` 首次发生可重试错误且后续尝试成功
- **THEN** `AgentRunner` 继续当前 `think`，图 iteration 不增加，且只提交一条成功的助手消息

#### Scenario: 重试不得重复桌面动作

- **WHEN** 前一轮已经成功执行桌面工具，下一轮 `think` 在首个流式增量前重试
- **THEN** Agent 不重新进入前一轮 `act`，也不重复执行该桌面工具

#### Scenario: 流式 HTTP 错误变成会话错误

- **WHEN** `/chat/completions` 返回不可重试非 2xx，或可重试错误达到最大重试次数
- **THEN** `AgentRunner.run` 返回的状态 `status` 为 `error`，且该状态被写入当前会话
