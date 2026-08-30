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

- **WHEN** `MAX_PROVIDER` 为 `modelscope`、`dashscope`、`openrouter` 或 `qiniu` 且端点拒绝连接
- **THEN** 客户端报告对应 provider 的网络与专属密钥检查提示，且不提示 `max-gui serve`

#### Scenario: 流式 HTTP 错误可读

- **WHEN** 流式 `/chat/completions` 返回非 2xx
- **THEN** 用户可见错误包含该状态码，且 MUST NOT 出现 `without having called read()`

### Requirement: 模型选择

系统 MUST 从独立 Python provider 定义取得当前模型名，运行时 `MODEL_NAME` MUST NOT
覆盖该值。`ollama` 模型 MUST 为 `qwen3.5:9b`，`openrouter` 模型 MUST 为
`qwen/qwen3.5-plus`，`qiniu` 模型 MUST 为 `z-ai/glm-5.3-flash`。系统 MUST NOT 提供
TUI `/model` 或 CLI `--model`，也 MUST NOT 检查主推理模型的本地权重目录。

#### Scenario: Ollama 默认模型

- **WHEN** `MAX_PROVIDER` 未设置或为 `ollama`
- **THEN** 请求使用 model id `qwen3.5:9b`

#### Scenario: OpenRouter 默认模型

- **WHEN** `MAX_PROVIDER=openrouter`
- **THEN** 请求使用 model id `qwen/qwen3.5-plus`

#### Scenario: 七牛默认模型

- **WHEN** `MAX_PROVIDER=qiniu`
- **THEN** 请求使用 model id `z-ai/glm-5.3-flash`

#### Scenario: 环境变量不覆盖模型

- **WHEN** `MAX_PROVIDER=openrouter` 且环境中另有 `MODEL_NAME=other-model`
- **THEN** 请求仍使用 `qwen/qwen3.5-plus`

### Requirement: 双推理后端

系统 MUST 根据 `MAX_PROVIDER` 从单一注册表选择 `ollama`、`modelscope`、`dashscope`、
`openrouter` 或 `qiniu`。所有 provider MUST 使用定义中的 OpenAI 兼容根端点与模型，并共用
`/chat/completions`、消息编码、SSE 解析、工具调用和 token 用量链路。具有密钥环境变量的
provider MUST 在启动 TUI 或首次请求前校验专属密钥；缺密钥 MUST 中文报错且不提示
`max-gui serve`。`ollama` MUST 使用 `http://192.168.1.158:11434/v1`、`qwen3.5:9b`，
不发送 Authorization 头；`openrouter` MUST 使用 `https://openrouter.ai/api/v1`、
`qwen/qwen3.5-plus` 与 `MAX_OPENROUTER_KEY`；`qiniu` MUST 使用
`https://api.qnaigc.com/v1`、`z-ai/glm-5.3-flash` 与 `MAX_QINIU_KEY`。

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

#### Scenario: qiniu 发送兼容请求

- **WHEN** `MAX_PROVIDER=qiniu` 且 `MAX_QINIU_KEY` 非空
- **THEN** 客户端向 `https://api.qnaigc.com/v1/chat/completions` 发请求，模型为 `z-ai/glm-5.3-flash`，带 Bearer 密钥且不检查主推理本地权重

#### Scenario: 云端缺专属密钥

- **WHEN** 选中的云端 provider 对应专属密钥为空
- **THEN** 系统报告包含对应密钥变量名的中文错误，不提示 `max-gui serve`，且不发起 HTTP 请求

## ADDED Requirements

### Requirement: 七牛请求复用工具 schema

当 `MAX_PROVIDER=qiniu` 且 Agent 工具注册表非空时，客户端 MUST 在 `/chat/completions`
请求中包含 `tools` 数组与 `tool_choice=auto`，并 MUST 按现有 SSE 规则拼装
`delta.tool_calls`；系统 MUST NOT 为七牛改用正文 JSON 工具调用协议。

#### Scenario: 七牛请求带 tools

- **WHEN** `MAX_PROVIDER=qiniu` 且注册表含桌面工具 schema
- **THEN** POST `https://api.qnaigc.com/v1/chat/completions` 的 JSON 含 `tools` 数组与 `tool_choice` 为 `auto`
