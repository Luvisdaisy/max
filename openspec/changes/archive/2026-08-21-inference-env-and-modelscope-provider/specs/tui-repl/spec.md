## ADDED Requirements

### Requirement: 模型由配置决定而非斜杠命令

TUI MUST NOT 提供 `/model` 命令。当前推理模型 MUST 来自已加载的 `MODEL_NAME`。用户提交 `/model` 或 `/model <名>` 时 MUST 按未知命令处理。

#### Scenario: /model 视为未知

- **WHEN** 用户提交 `/model` 或 `/model qwen3.5-2b`
- **THEN** TUI 在记录区显示命令未找到，且不改变当前推理模型，且不调用模型补全

## MODIFIED Requirements

### Requirement: 斜杠命令

TUI SHALL 至少支持 `/new`、`/sessions`、`/attach`、`/interrupt`、`/quit`。未知命令 MUST 在记录区显示错误，且 MUST NOT 启动 Agent 运行。TUI MUST NOT 将 `/model` 列为受支持命令。

#### Scenario: 开始新会话

- **WHEN** 用户提交 `/new`
- **THEN** TUI 创建新的空会话（新的时间戳 JSON）并清空记录区

#### Scenario: 中断一次运行

- **WHEN** Agent 正在运行且用户提交 `/interrupt`
- **THEN** 运行停止，记录区保留已收到的 token，会话标记为 interrupted

#### Scenario: 未知命令

- **WHEN** 用户提交 `/not-a-command`
- **THEN** TUI 显示命令未找到，且不调用模型
