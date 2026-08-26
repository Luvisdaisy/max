## MODIFIED Requirements

### Requirement: OpenAI 兼容客户端

系统 SHALL 让全部已注册 provider 调用各自定义的 OpenAI 兼容 `/chat/completions` 端点。客户端 MUST 按配置发送 `model`、`messages`、`stream`。连接失败 MUST 作为用户可见错误报告，且 MUST NOT 让 TUI 崩溃。仅 provider 定义要求本地启动提示时，错误 MUST 提示建议的 `max-gui serve` 命令。流式请求遇到 HTTP 非 2xx 时，客户端 MUST 读取响应正文（不得访问未 `read()` 的流式 `response.text`），并把状态码与截断后的正文展示给用户。

#### Scenario: 成功流式输出

- **WHEN** 任一已注册 provider 端点可达并返回 SSE token 流
- **THEN** 客户端按顺序产出 token，直到流结束

#### Scenario: 本地服务不可达

- **WHEN** `MAX_PROVIDER=local` 且定义的本机端点拒绝连接
- **THEN** 客户端抛出已处理错误，TUI 展示该错误并提示建议的 `max-gui serve` 命令

#### Scenario: 云端服务不可达

- **WHEN** `MAX_PROVIDER` 为 `modelscope`、`dashscope` 或 `openrouter` 且端点拒绝连接
- **THEN** 客户端报告对应 provider 的网络与专属密钥检查提示，且不提示 `max-gui serve`

#### Scenario: 流式 HTTP 错误可读

- **WHEN** 流式 `/chat/completions` 返回非 2xx
- **THEN** 用户可见错误包含该状态码，且 MUST NOT 出现 `without having called read()`

### Requirement: 模型选择

系统 MUST 从独立 Python provider 定义取得当前模型名，运行时 `MODEL_NAME` MUST NOT 覆盖该值。`local` 模型 MUST 为完整目录名 `qwen3.5-4b`，权重路径为 `model/qwen3.5-4b`；系统 MUST NOT 将短别名解释为其它目录。`openrouter` 模型 MUST 为 `qwen/qwen3.5-plus`。本地权重缺失 MUST 报告包含该目录路径的错误，MUST NOT 提及 `max-gui download`。自动化测试 MUST 仍可通过显式构造 `Settings` 钉死占位权重。系统 MUST NOT 提供 TUI `/model` 或 CLI `--model`。

#### Scenario: local 默认模型

- **WHEN** `MAX_PROVIDER=local`
- **THEN** 请求使用 model id `qwen3.5-4b`，权重目录为 `model/qwen3.5-4b`

#### Scenario: OpenRouter 默认模型

- **WHEN** `MAX_PROVIDER=openrouter`
- **THEN** 请求使用 model id `qwen/qwen3.5-plus`

#### Scenario: 环境变量不覆盖模型

- **WHEN** `MAX_PROVIDER=openrouter` 且环境中另有 `MODEL_NAME=other-model`
- **THEN** 请求仍使用 `qwen/qwen3.5-plus`

#### Scenario: 权重缺失

- **WHEN** `local` provider 定义的模型没有完整本地权重目录
- **THEN** 系统报告包含 `model/qwen3.5-4b` 路径的错误，且不发送请求，且不含 download 命令

### Requirement: serve 与 download 辅助命令

CLI SHALL 提供 `max-gui serve`，仅当选中 provider 定义允许 `serve` 时以 OpenAI 兼容模式启动 vLLM，并带上配置的 `--max-model-len`、`--gpu-memory-utilization`、`--dtype`。开发默认加载 `model/qwen3.5-4b`。vLLM 可执行文件 MUST 按 `MAX_GUI_VLLM`、`PATH` 中的 `vllm`、`~/.venv-vllm-metal/bin/vllm` 的顺序解析，MUST NOT 回退到当前解释器的 `python -m vllm`。找不到可执行文件时 MUST 以非零退出码报中文错误。不允许 `serve` 的 provider MUST 以非零退出码失败并提示修改 `.env`。CLI MUST NOT 提供 `max-gui download` 子命令。

#### Scenario: 启动已配置模型

- **WHEN** `MAX_PROVIDER=local`，用户执行 `max-gui serve` 且权重存在，并且能解析到 vLLM 可执行文件
- **THEN** 使用该二进制以配置的模型路径启动 OpenAI 兼容 HTTP API，并开启 `--enable-auto-tool-choice` 与 `--tool-call-parser qwen3_coder`

#### Scenario: 云端 provider 拒绝 serve

- **WHEN** `MAX_PROVIDER` 为 `modelscope`、`dashscope` 或 `openrouter` 且用户执行 `max-gui serve`
- **THEN** 命令以非零退出码失败，错误信息提示将 `MAX_PROVIDER` 改为 `local`

#### Scenario: remote 拒绝 serve

- **WHEN** `MAX_PROVIDER=remote` 且用户执行 `max-gui serve`
- **THEN** 命令以非零退出码失败，错误信息提示将 `MAX_PROVIDER` 改为 `local`

#### Scenario: 未激活独立 vLLM 环境

- **WHEN** `MAX_PROVIDER=local`，PATH 中没有 `vllm`，但 `~/.venv-vllm-metal/bin/vllm` 存在
- **THEN** `max-gui serve` 仍使用该默认路径启动，而不是项目 `.venv` 的 Python

#### Scenario: 找不到 vLLM

- **WHEN** `MAX_PROVIDER=local` 且 `MAX_GUI_VLLM`、PATH 与默认路径都没有可用的 vLLM 可执行文件
- **THEN** 命令以非零退出码失败，错误信息提示 `source ~/.venv-vllm-metal/bin/activate` 或设置 `MAX_GUI_VLLM`

#### Scenario: download 子命令不存在

- **WHEN** 用户执行 `max-gui download`
- **THEN** CLI 不以成功下载结束；该子命令 MUST 不再作为受支持的入口

### Requirement: 双推理后端

系统 MUST 根据 `MAX_PROVIDER` 从单一注册表选择 `local`、`remote`、`modelscope`、`dashscope` 或 `openrouter`。所有 provider MUST 使用定义中的 OpenAI 兼容根端点与模型，并共用 `/chat/completions`、消息编码、SSE 解析、工具调用和 token 用量链路。仅 `local` MUST 在发请求前检查本地权重。具有密钥环境变量的 provider MUST 在启动 TUI 或首次请求前校验专属密钥；缺密钥 MUST 中文报错且不提示 `max-gui serve`。`openrouter` MUST 使用 `https://openrouter.ai/api/v1`、`qwen/qwen3.5-plus` 与 `MAX_OPENROUTER_KEY`。

#### Scenario: local 仍检查权重

- **WHEN** `MAX_PROVIDER=local` 且对应目录无完整权重
- **THEN** 客户端不发送请求，错误信息包含路径 `model/qwen3.5-4b`，且不含 `max-gui download`

#### Scenario: remote 不检查权重且不发送认证头

- **WHEN** `MAX_PROVIDER=remote`
- **THEN** 客户端向注册表定义的局域网端点发请求，不检查本地权重且不发送 Authorization 头

#### Scenario: modelscope 使用专属密钥

- **WHEN** `MAX_PROVIDER=modelscope` 且 `MAX_MODELSCOPE_KEY` 非空
- **THEN** 客户端向魔搭端点发送 `/chat/completions`，请求模型来自 provider 定义且带 Bearer 密钥

#### Scenario: dashscope 使用代码内专属端点

- **WHEN** `MAX_PROVIDER=dashscope` 且 `MAX_DASHSCOPE_KEY` 非空
- **THEN** 客户端向 provider 定义的北京专属端点发送 `/chat/completions`，且不检查本地权重

#### Scenario: openrouter 发送兼容请求

- **WHEN** `MAX_PROVIDER=openrouter` 且 `MAX_OPENROUTER_KEY` 非空
- **THEN** 客户端向 `https://openrouter.ai/api/v1/chat/completions` 发请求，模型为 `qwen/qwen3.5-plus`，带 Bearer 密钥且不检查本地权重

#### Scenario: 云端缺专属密钥

- **WHEN** 选中的云端 provider 对应专属密钥为空
- **THEN** 系统报告包含对应密钥变量名的中文错误，不提示 `max-gui serve`，且不发起 HTTP 请求

### Requirement: 云端与本地均发送工具 schema

当 Agent 调用推理且工具注册表非空时，客户端 MUST 在请求中包含 `tools` 与 `tool_choice=auto`，无论选中哪个已注册 provider。解析 SSE 时 MUST 按现有规则拼装 `tool_calls`。系统 MUST NOT 因云端后端而改为从正文 JSON 解析工具调用。

#### Scenario: OpenRouter 请求带 tools

- **WHEN** `MAX_PROVIDER=openrouter` 且注册表含桌面工具 schema
- **THEN** POST `/chat/completions` 的 JSON 含 `tools` 数组与 `tool_choice` 为 `auto`

#### Scenario: 其它 provider 请求带 tools

- **WHEN** `MAX_PROVIDER` 为 `local`、`remote`、`modelscope` 或 `dashscope` 且注册表含桌面工具 schema
- **THEN** POST `/chat/completions` 的 JSON 含 `tools` 数组与 `tool_choice` 为 `auto`

#### Scenario: 流式 tool_calls 拼装

- **WHEN** 任一兼容端点的 SSE 推送带 `index` 的 `delta.tool_calls` 增量
- **THEN** 客户端产出的完整回复含拼好的 `tool_calls`，可供 Agent `act` 使用
