## ADDED Requirements

### Requirement: 独立的桌面自动批准开关

会话 JSON MUST 持久化 `auto_approve_desktop`，缺省为 `false`。该字段 MUST 与 `auto_approve` 分开读写。缺少该字段的旧会话 MUST 视为 `false`，且 MUST 仍能加载。

#### Scenario: 新会话默认关闭桌面自动批准

- **WHEN** 系统创建新会话
- **THEN** 会话 JSON 中 `auto_approve_desktop` 为 `false`

#### Scenario: 旧会话缺字段仍可加载

- **WHEN** 已存会话 JSON 没有 `auto_approve_desktop`
- **THEN** store 成功加载该会话，并把桌面自动批准视为关闭
