## MODIFIED Requirements

### Requirement: OpenAI 兼容客户端

系统 SHALL 让全部已注册 provider 调用各自定义的 OpenAI 兼容 `/chat/completions` 端点。
客户端 MUST 按配置发送 `model`、`messages`、`stream`。连接失败 MUST 作为用户可见错误
报告，且 MUST NOT 让 TUI 崩溃。流式请求遇到 HTTP 非 2xx 时，客户端 MUST 读取响应正文
（不得访问未 `read()` 的流式 `response.text`），并把状态码与截断后的正文展示给用户。

#### Scenario: 成功流式输出

- **WHEN** 任一已注册 provider 端点可达并返回 SSE token 流
- **THEN** 客户端按顺序产出 token，直到流结束

#### Scenario: Ollama 服务不可达

- **WHEN** `MAX_PROVIDER=ollama` 且定义的局域网端点拒绝连接
- **THEN** 客户端抛出已处理错误，TUI 展示 WSL Ollama、Windows 防火墙与局域网端口检查提示，且不提示 `max-gui serve`

#### Scenario: 云端服务不可达

- **WHEN** `MAX_PROVIDER` 为 `modelscope`、`dashscope` 或 `openrouter` 且端点拒绝连接
- **THEN** 客户端报告对应 provider 的网络与专属密钥检查提示，且不提示 `max-gui serve`

#### Scenario: 流式 HTTP 错误可读

- **WHEN** 流式 `/chat/completions` 返回非 2xx
- **THEN** 用户可见错误包含该状态码，且 MUST NOT 出现 `without having called read()`

### Requirement: 模型选择

系统 MUST 从独立 Python provider 定义取得当前模型名，运行时 `MODEL_NAME` MUST NOT
覆盖该值。`ollama` 模型 MUST 为 `qwen3.5:9b`，`openrouter` 模型 MUST 为
`qwen/qwen3.5-plus`。系统 MUST NOT 提供 TUI `/model` 或 CLI `--model`，也 MUST NOT
检查主推理模型的本地权重目录。

#### Scenario: Ollama 默认模型

- **WHEN** `MAX_PROVIDER` 未设置或为 `ollama`
- **THEN** 请求使用 model id `qwen3.5:9b`

#### Scenario: OpenRouter 默认模型

- **WHEN** `MAX_PROVIDER=openrouter`
- **THEN** 请求使用 model id `qwen/qwen3.5-plus`

#### Scenario: 环境变量不覆盖模型

- **WHEN** `MAX_PROVIDER=openrouter` 且环境中另有 `MODEL_NAME=other-model`
- **THEN** 请求仍使用 `qwen/qwen3.5-plus`

### Requirement: 双推理后端

系统 MUST 根据 `MAX_PROVIDER` 从单一注册表选择 `ollama`、`modelscope`、`dashscope` 或
`openrouter`。所有 provider MUST 使用定义中的 OpenAI 兼容根端点与模型，并共用
`/chat/completions`、消息编码、SSE 解析、工具调用和 token 用量链路。具有密钥环境变量
的 provider MUST 在启动 TUI 或首次请求前校验专属密钥；缺密钥 MUST 中文报错且不提示
`max-gui serve`。`ollama` MUST 使用 `http://192.168.1.158:11434/v1`、`qwen3.5:9b`，
不发送 Authorization 头；`openrouter` MUST 使用 `https://openrouter.ai/api/v1`、
`qwen/qwen3.5-plus` 与 `MAX_OPENROUTER_KEY`。

#### Scenario: Ollama 不发送认证头

- **WHEN** `MAX_PROVIDER=ollama`
- **THEN** 客户端向注册表定义的局域网端点发请求，不检查主推理本地权重且不发送 Authorization 头

#### Scenario: modelscope 使用专属密钥

- **WHEN** `MAX_PROVIDER=modelscope` 且 `MAX_MODELSCOPE_KEY` 非空
- **THEN** 客户端向魔搭端点发送 `/chat/completions`，请求模型来自 provider 定义且带 Bearer 密钥

#### Scenario: dashscope 使用代码内专属端点

- **WHEN** `MAX_PROVIDER=dashscope` 且 `MAX_DASHSCOPE_KEY` 非空
- **THEN** 客户端向 provider 定义的北京专属端点发送 `/chat/completions`，且不检查主推理本地权重

#### Scenario: openrouter 发送兼容请求

- **WHEN** `MAX_PROVIDER=openrouter` 且 `MAX_OPENROUTER_KEY` 非空
- **THEN** 客户端向 `https://openrouter.ai/api/v1/chat/completions` 发请求，模型为 `qwen/qwen3.5-plus`，带 Bearer 密钥且不检查主推理本地权重

#### Scenario: 云端缺专属密钥

- **WHEN** 选中的云端 provider 对应专属密钥为空
- **THEN** 系统报告包含对应密钥变量名的中文错误，不提示 `max-gui serve`，且不发起 HTTP 请求

### Requirement: 云端与本地均发送工具 schema

当 Agent 调用推理且工具注册表非空时，客户端 MUST 在请求中包含 `tools` 与
`tool_choice=auto`，无论选中哪个已注册 provider。解析 SSE 时 MUST 按现有规则拼装
`tool_calls`。系统 MUST NOT 因 provider 而改为从正文 JSON 解析工具调用。

#### Scenario: OpenRouter 请求带 tools

- **WHEN** `MAX_PROVIDER=openrouter` 且注册表含桌面工具 schema
- **THEN** POST `/chat/completions` 的 JSON 含 `tools` 数组与 `tool_choice` 为 `auto`

#### Scenario: 其它 provider 请求带 tools

- **WHEN** `MAX_PROVIDER` 为 `ollama`、`modelscope` 或 `dashscope` 且注册表含桌面工具 schema
- **THEN** POST `/chat/completions` 的 JSON 含 `tools` 数组与 `tool_choice` 为 `auto`

#### Scenario: 流式 tool_calls 拼装

- **WHEN** 任一兼容端点的 SSE 推送带 `index` 的 `delta.tool_calls` 增量
- **THEN** 客户端产出的完整回复含拼好的 `tool_calls`，可供 Agent `act` 使用

### Requirement: dashscope 回传思考字段

当 `MAX_PROVIDER=dashscope` 且助手消息 content 含非空 `reasoning` 时，系统 MUST 让
`to_chat_messages` 在该条请求消息上设置独立字段 `reasoning_content`，其值等于已存思考
文本；`content` MUST 仍为正文，MUST NOT 把思考拼进 `content`。无思考的助手消息 MUST
NOT 带 `reasoning_content`。其它已注册 provider MUST NOT 把思考编进请求。

#### Scenario: dashscope 助手带 reasoning_content

- **WHEN** `MAX_PROVIDER=dashscope`，助手 content 为 `{text: "你好", reasoning: "先问候"}`
- **THEN** 编码结果该条含 `content` 为 `你好`，且 `reasoning_content` 为 `先问候`

#### Scenario: dashscope 无思考不加字段

- **WHEN** `MAX_PROVIDER=dashscope`，助手 content 仅有 `text`、无 `reasoning`
- **THEN** 编码结果该条不含 `reasoning_content`

#### Scenario: 非 DashScope 不回传思考

- **WHEN** `MAX_PROVIDER=ollama`，助手 content 含 `reasoning`
- **THEN** 编码结果该条无 `reasoning_content`，`content` 仅为正文

## REMOVED Requirements

### Requirement: serve 与 download 辅助命令

**Reason**：主推理不再支持本机 `local` provider 或由 CLI 启动主模型 vLLM。

**Migration**：删除 `max-gui serve` 调用；使用 WSL Ollama 服务，或在 `.env` 选择并配置保留的云端 provider。
