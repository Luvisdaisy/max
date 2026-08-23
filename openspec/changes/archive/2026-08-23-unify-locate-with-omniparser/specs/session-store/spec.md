## MODIFIED Requirements

### Requirement: 持久化文字定位命中表

会话 JSON MUST 持久化最近一次成功 `locate` 的编号到逻辑中心映射。缺字段的旧会话 MUST 视为空表。下一次成功定位 MUST 覆盖旧表。模型直接调用的成功 `screenshot` 以及破坏性动作的后置截图 MUST 把该字段写成空表。

#### Scenario: 定位结果可恢复

- **WHEN** 会话保存时已有 `id=1` 的定位中心
- **THEN** 重新加载后 `mouse_move` 的 `target_id=1` 仍指向同一逻辑中心

#### Scenario: 截图后命中表为空

- **WHEN** 会话先保存了定位表，随后一次由模型调用的成功 `screenshot` 结束并保存会话
- **THEN** 该会话 JSON 的定位表为空
