## ADDED Requirements

### Requirement: 记录区不展示执行元数据

TUI 展示 `role=tool` 的消息时 MUST 使用 `content.text`（可截断），MUST NOT 把 `exec` 对象当作记录区正文。状态区 MUST NOT 展示 `artifacts/runs/` 路径。

#### Scenario: 工具结果只显示摘要文本

- **WHEN** 一条 tool 消息含截图 JSON 摘要与 `exec.duration_ms`
- **THEN** 记录区可见该摘要文本，且 MUST NOT 把 `duration_ms` 作为独立日志行写出

#### Scenario: 回合开始不指向 runs 文件

- **WHEN** 用户提交一条非空文本并开始 Agent 运行
- **THEN** 状态区文本不含 `artifacts/runs/`
