## MODIFIED Requirements

### Requirement: 独立的桌面自动批准开关

会话 JSON MUST 仍持久化 `auto_approve` 与 `auto_approve_desktop`，缺省为 `false`，二者分开读写。缺少字段的旧会话 MUST 视为 `false` 且仍能加载。这两个字段 MUST NOT 再作为工具是否执行的依据。

#### Scenario: 新会话仍写入字段

- **WHEN** 系统创建新会话
- **THEN** 会话 JSON 中 `auto_approve` 与 `auto_approve_desktop` 为 `false`

#### Scenario: 旧会话缺字段仍可加载

- **WHEN** 已存会话 JSON 没有 `auto_approve_desktop`
- **THEN** store 成功加载该会话

## ADDED Requirements

### Requirement: 推理失败写入会话错误

当 `think` 因推理客户端异常结束时，会话 JSON 的 `status` MUST 为 `error`，MUST 写入可读错误说明，检查点 MUST 反映当时已提交的消息。MUST NOT 把上一回合的 `done` 与过期检查点留在磁盘上假装本回合成功。

#### Scenario: 多轮后推理 400 落盘

- **WHEN** 本回合已执行若干工具，下一轮 `think` 收到推理服务非 2xx
- **THEN** 保存后的会话 `status` 为 `error`，`error` 或检查点中含状态码或正文摘要，消息列表含已执行的工具结果
