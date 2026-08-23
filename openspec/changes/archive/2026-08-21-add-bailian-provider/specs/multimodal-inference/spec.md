## ADDED Requirements

### Requirement: bailian 回传思考字段

当 `MAX_PROVIDER=bailian` 且助手消息 content 含非空 `reasoning` 时，`to_chat_messages` MUST 在该条请求消息上设置独立字段 `reasoning_content`，其值等于已存思考文本；`content` MUST 仍为正文，MUST NOT 把思考拼进 `content`。无思考的助手消息 MUST NOT 带 `reasoning_content`。`local` 与 `modelscope` MUST 仍不把思考编进请求。

#### Scenario: bailian 助手带 reasoning_content

- **WHEN** `MAX_PROVIDER=bailian`，助手 content 为 `{text: "你好", reasoning: "先问候"}`
- **THEN** 编码结果该条含 `content` 为 `你好`，且 `reasoning_content` 为 `先问候`

#### Scenario: bailian 无思考不加字段

- **WHEN** `MAX_PROVIDER=bailian`，助手 content 仅有 `text`、无 `reasoning`
- **THEN** 编码结果该条不含 `reasoning_content`

#### Scenario: local 仍不回传思考

- **WHEN** `MAX_PROVIDER=local`，助手 content 含 `reasoning`
- **THEN** 编码结果该条无 `reasoning_content`，`content` 仅为正文

## MODIFIED Requirements

### Requirement: serve 与 download 辅助命令

CLI SHALL 提供 `max-gui serve`，仅当 `MAX_PROVIDER=local` 时以 OpenAI 兼容模式启动 vLLM，并带上配置的 `--max-model-len`、`--gpu-memory-utilization`、`--dtype`。开发默认加载 `model/qwen3.5-4b`。vLLM 可执行文件 MUST 按 `MAX_GUI_VLLM`、`PATH` 中的 `vllm`、`~/.venv-vllm-metal/bin/vllm` 的顺序解析，MUST NOT 回退到当前解释器的 `python -m vllm`。找不到可执行文件时 MUST 以非零退出码报中文错误。`MAX_PROVIDER` 为 `modelscope` 或 `bailian` 时 `max-gui serve` MUST 以非零退出码失败并提示修改 `.env`。CLI MUST NOT 提供 `max-gui download` 子命令。

#### Scenario: 启动已配置模型

- **WHEN** `MAX_PROVIDER=local`，用户执行 `max-gui serve` 且权重存在，并且能解析到 vLLM 可执行文件
- **THEN** 使用该二进制以配置的模型路径启动 OpenAI 兼容 HTTP API，并开启 `--enable-auto-tool-choice` 与 `--tool-call-parser qwen3_coder`；未指定 `MODEL_NAME` 时路径为 `model/qwen3.5-4b`

#### Scenario: modelscope 下拒绝 serve

- **WHEN** `MAX_PROVIDER=modelscope` 且用户执行 `max-gui serve`
- **THEN** 命令以非零退出码失败，错误信息提示将 `MAX_PROVIDER` 改为 `local`

#### Scenario: bailian 下拒绝 serve

- **WHEN** `MAX_PROVIDER=bailian` 且用户执行 `max-gui serve`
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

系统 MUST 根据 `MAX_PROVIDER` 选择后端。`local` MUST 使用可配置的本机 OpenAI 兼容端点（缺省 `http://127.0.0.1:8000/v1`），并在发请求前确认 `model/<MODEL_NAME>` 权重完整。`modelscope` MUST 使用 `https://api-inference.modelscope.cn/v1`，MUST 将请求中的 `model` 设为 `MODEL_NAME` 原文，MUST NOT 检查本地权重目录。`modelscope` 且 `MAX_PROVIDER_KEY` 为空时，MUST 在启动 TUI 或首次请求前以中文报错，MUST NOT 提示 `max-gui serve`。`bailian` MUST 使用 `https://{MAX_BAILIAN_WORKSPACE}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`，MUST 将请求中的 `model` 设为 `MODEL_NAME` 原文，MUST NOT 检查本地权重目录。`bailian` 且 `MAX_PROVIDER_KEY` 为空时，MUST 在启动 TUI 或首次请求前以中文报错，MUST NOT 提示 `max-gui serve`。三种后端 MUST 共用同一套消息编码与流式解析（`bailian` 的思考回传除外），MUST NOT 为云端省略 `tools`。

#### Scenario: local 仍检查权重

- **WHEN** `MAX_PROVIDER=local` 且 `MODEL_NAME=qwen3.5-4b`，对应目录无完整权重
- **THEN** 客户端不发送请求，错误信息包含路径 `model/qwen3.5-4b`，且不含 `max-gui download`

#### Scenario: modelscope 不检查本地权重

- **WHEN** `MAX_PROVIDER=modelscope`、`MAX_PROVIDER_KEY` 非空，且仓库没有 `model/Qwen/Qwen3.8-27B`
- **THEN** 客户端仍向魔搭端点发出 `/chat/completions`，请求 `model` 为当前 `MODEL_NAME`

#### Scenario: modelscope 缺密钥

- **WHEN** `MAX_PROVIDER=modelscope` 且 `MAX_PROVIDER_KEY` 为空
- **THEN** 系统报告中文缺密钥错误，不提示 `max-gui serve`，不发起 HTTP 请求

#### Scenario: modelscope 连接失败不提 serve

- **WHEN** `MAX_PROVIDER=modelscope` 且魔搭端点拒绝连接
- **THEN** 用户可见错误不包含 `max-gui serve`

#### Scenario: bailian 使用北京专属域名

- **WHEN** `MAX_PROVIDER=bailian`、`MAX_BAILIAN_WORKSPACE=llm-demo`、`MAX_PROVIDER_KEY` 非空
- **THEN** 客户端向 `https://llm-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions` 发请求，`model` 为当前 `MODEL_NAME`，且不检查 `model/qwen3.8-27b`

#### Scenario: bailian 缺密钥

- **WHEN** `MAX_PROVIDER=bailian` 且 `MAX_PROVIDER_KEY` 为空
- **THEN** 系统报告中文缺密钥错误，不提示 `max-gui serve`，不发起 HTTP 请求

#### Scenario: bailian 连接失败不提 serve

- **WHEN** `MAX_PROVIDER=bailian` 且百炼端点拒绝连接
- **THEN** 用户可见错误不包含 `max-gui serve`

### Requirement: 云端与本地均发送工具 schema

当 Agent 调用推理且工具注册表非空时，客户端 MUST 在请求中包含 `tools` 与 `tool_choice=auto`，无论 `MAX_PROVIDER` 为 `local`、`modelscope` 还是 `bailian`。解析 SSE 时 MUST 按现有规则拼装 `tool_calls`。系统 MUST NOT 因云端后端而改为从正文 JSON 解析工具调用。

#### Scenario: modelscope 请求带 tools

- **WHEN** `MAX_PROVIDER=modelscope` 且注册表含桌面工具 schema
- **THEN** POST `/chat/completions` 的 JSON 含 `tools` 数组与 `tool_choice` 为 `auto`

#### Scenario: bailian 请求带 tools

- **WHEN** `MAX_PROVIDER=bailian` 且注册表含桌面工具 schema
- **THEN** POST `/chat/completions` 的 JSON 含 `tools` 数组与 `tool_choice` 为 `auto`

#### Scenario: 云端流式 tool_calls 拼装

- **WHEN** 魔搭或百炼兼容 SSE 推送带 `index` 的 `delta.tool_calls` 增量
- **THEN** 客户端产出的完整回复含拼好的 `tool_calls`，可供 Agent `act` 使用
