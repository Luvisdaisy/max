## ADDED Requirements

### Requirement: 图执行期间发出进度

`AgentRunner` 在每个节点进入时 MUST 回调当前状态名（`thinking` / `acting` / `observing`）。流式思考与正文 MUST 在 `think` 等待模型期间分别回调。一条助手消息在 `think` 拼装完成后 MUST 立即回调 `on_message`。`act` 中每完成一次 `registry.invoke` MUST 立即回调该条 tool 消息，MUST NOT 等到本节点全部工具结束。

#### Scenario: 状态随节点变化

- **WHEN** 模型返回工具调用并进入 `act`
- **THEN** 在工具执行前调用方已收到状态 `acting`

#### Scenario: 单次工具完成后即可见

- **WHEN** 一次 `think` 请求了两个工具且 `act` 顺序执行
- **THEN** 第一个工具返回后，调用方在第二个工具返回前已收到该 tool 的 `on_message`

### Requirement: think 与 act 增量持久化

`think` 产生助手消息后 MUST 立刻写入当前会话 JSON。`act` 每完成一个工具 MUST 立刻将该 tool 消息写入当前会话 JSON。图正常结束时 MUST 更新 `status` 与检查点，MUST NOT 把已写入的同一条消息再追加一次。

#### Scenario: 工具循环中途会话已有助手消息

- **WHEN** 模型返回带工具调用的助手消息且 `act` 尚未全部完成
- **THEN** 该会话 JSON 已包含这条助手消息

#### Scenario: 结束不重复追加

- **WHEN** 一回合含一次工具循环后以无工具调用结束
- **THEN** 会话 JSON 中该助手与 tool 消息各出现一次
