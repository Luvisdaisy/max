## MODIFIED Requirements

### Requirement: 推理失败写入会话错误

当 `think` 因不可重试推理错误、有效流式增量后的断流或重试耗尽而结束时，会话 JSON 的 `status` MUST 为 `error`，MUST 写入可读错误说明与已重试次数，检查点 MUST 反映当时已提交的消息。重试过程中 MUST NOT 追加重复 user、assistant 或 tool 消息；后续尝试成功时 MUST 只提交成功结果对应的一条助手消息。MUST NOT 把上一回合的 `done` 与过期检查点留在磁盘上假装本回合成功。

#### Scenario: 多轮后推理 400 重试耗尽落盘

- **WHEN** 本回合已执行若干工具，下一轮 `think` 连续收到可重试推理错误并达到最大次数
- **THEN** 保存后的会话 `status` 为 `error`，错误或检查点中含最后状态码、正文摘要和重试次数，消息列表含已执行的工具结果且没有重复项

#### Scenario: 重试成功只保存一次助手消息

- **WHEN** 同一次 `think` 的前两次网络尝试失败且第三次成功
- **THEN** 会话不保存失败尝试内容，只追加第三次成功结果对应的一条助手消息
