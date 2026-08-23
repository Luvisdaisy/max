## ADDED Requirements

### Requirement: 会话 model 字段不覆盖运行时配置

创建会话时 MUST 把当时配置中的 `MODEL_NAME` 写入会话 JSON 的 `model` 字段作为盖章。列出或切换会话 MUST 加载该会话消息，MUST NOT 根据会话内 `model` 修改当前 `Settings` 的 provider 或 `MODEL_NAME`。后续推理 MUST 仍使用启动时从 `.env` / 环境变量加载的模型。

#### Scenario: 切换旧会话不改推理模型

- **WHEN** 当前配置 `MODEL_NAME` 为 `qwen3.5-4b`，用户切换到 `model` 字段为其它值（含历史短别名）的已存会话
- **THEN** 记录区显示该会话消息，但随后的 think 请求仍使用 `qwen3.5-4b`

#### Scenario: 新会话盖章当前模型名

- **WHEN** 用户提交 `/new` 且当前 `MODEL_NAME` 为 `Qwen/Qwen3.8-27B`
- **THEN** 新建会话 JSON 的 `model` 为 `Qwen/Qwen3.8-27B`

## MODIFIED Requirements

### Requirement: 列出并切换会话

系统 MUST 列出已存会话（id、title、updated_at），并 MUST 能把当前 TUI 会话切到指定 id，加载该会话消息。切换会话 MUST NOT 改变进程内已加载的推理后端与 `MODEL_NAME`。

#### Scenario: 列出会话

- **WHEN** 用户执行 `/sessions`
- **THEN** TUI 展示已存会话的标题与时间戳

#### Scenario: 切换会话

- **WHEN** 用户选择一个已存在的会话 id
- **THEN** 记录区替换为该会话消息，后续回合追加到对应 JSON 文件，当前推理模型仍为配置中的 `MODEL_NAME`
