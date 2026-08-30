## MODIFIED Requirements

### Requirement: 流式展示助手 token

TUI SHALL 在 token 到达时渲染进行中的助手条目。思考增量与正文增量 MUST 立即可见，不等待该次
`think` 完整完成。该次 `think` 结束后 MUST 将进行中条目写入记录区；最终助手记录 MUST NOT
显示 `reasoning` 内容。

#### Scenario: token 级展示

- **WHEN** 推理客户端产出一个正文 token
- **THEN** 进行中的助手展示立即更新，不等待完整完成

#### Scenario: 思考 token 级展示

- **WHEN** 推理客户端产出一个思考 token
- **THEN** 进行中的助手展示立即更新，且该 token 出现在思考分区

#### Scenario: 提交后不显示思考

- **WHEN** 含 reasoning 与正文的进行中助手条目完成并写入记录区
- **THEN** 记录区仅显示助手正文，且不显示该 reasoning

### Requirement: 逐步展示思考、正文与工具

TUI MUST 在思考 token 到达时更新进行中的助手展示（与正文分区，思考带「思考」标识）。一次
`think` 结束后 MUST 把该次思考与正文作为一条助手消息提交，并清空进行中区域；记录区仅渲染该
助手消息的正文，不渲染其 reasoning。工具结果 MUST 在该次 `act` 完成当时写入记录区。同一用户
回合内多次 `think` MUST 成为多条助手记录，MUST NOT 拼成一条。状态区 MUST 显示「思考中…」
「执行工具…」「观察中…」中与当前节点对应的文案。恢复已保存会话时，助手消息也 MUST 仅显示正文，
即使其持久化内容含 reasoning。

#### Scenario: 长思考过程中记录区已有进行中文本

- **WHEN** 推理客户端正在推送思考或正文 token 且本轮 `think` 尚未结束
- **THEN** 进行中区域可见已到达的文本，记录区尚未把本次 think 落成最终助手条目

#### Scenario: 工具结果不等待整回合

- **WHEN** Agent 正在执行第一个工具且后续还有 think
- **THEN** 记录区已出现该工具结果摘要

#### Scenario: 两轮 think 两条助手记录

- **WHEN** 一回合内模型先调工具再给出最终文本
- **THEN** 记录区有两条助手消息，第二条为最终文本，且两条消息均不显示 reasoning

#### Scenario: 恢复含思考的会话

- **WHEN** 用户打开一份助手消息含 reasoning 与正文的已保存会话
- **THEN** 记录区显示该助手正文，且不显示 reasoning

#### Scenario: 状态栏进入执行工具

- **WHEN** Agent 从 `think` 进入 `act`
- **THEN** 状态区文案为「执行工具…」
