## ADDED Requirements

### Requirement: 双推理后端

系统 MUST 根据 `MAX_PROVIDER` 选择后端。`local` MUST 使用可配置的本机 OpenAI 兼容端点（缺省 `http://127.0.0.1:8000/v1`），并在发请求前确认 `model/<MODEL_NAME>` 权重完整。`modelscope` MUST 使用 `https://api-inference.modelscope.cn/v1`，MUST 将请求中的 `model` 设为 `MODEL_NAME` 原文，MUST NOT 检查本地权重目录。`modelscope` 且 `MAX_PROVIDER_KEY` 为空时，MUST 在启动 TUI 或首次请求前以中文报错，MUST NOT 提示 `max-gui serve`。两种后端 MUST 共用同一套消息编码与流式解析，MUST NOT 为云端省略 `tools`。

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

### Requirement: 云端与本地均发送工具 schema

当 Agent 调用推理且工具注册表非空时，客户端 MUST 在请求中包含 `tools` 与 `tool_choice=auto`，无论 `MAX_PROVIDER` 为 `local` 还是 `modelscope`。解析 SSE 时 MUST 按现有规则拼装 `tool_calls`。系统 MUST NOT 因云端后端而改为从正文 JSON 解析工具调用。

#### Scenario: modelscope 请求带 tools

- **WHEN** `MAX_PROVIDER=modelscope` 且注册表含桌面工具 schema
- **THEN** POST `/chat/completions` 的 JSON 含 `tools` 数组与 `tool_choice` 为 `auto`

#### Scenario: 云端流式 tool_calls 拼装

- **WHEN** 魔搭兼容 SSE 推送带 `index` 的 `delta.tool_calls` 增量
- **THEN** 客户端产出的完整回复含拼好的 `tool_calls`，可供 Agent `act` 使用

## MODIFIED Requirements

### Requirement: OpenAI 兼容客户端

系统 SHALL 调用可配置的 OpenAI 兼容 Chat Completions 端点。客户端 MUST 按配置发送 `model`、`messages`、`stream`。连接失败 MUST 作为用户可见错误报告，且 MUST NOT 让 TUI 崩溃。`MAX_PROVIDER=local` 且本机端点不可达时，错误 MUST 提示建议的 `max-gui serve` 命令。流式请求遇到 HTTP 非 2xx 时，客户端 MUST 读取响应正文（不得访问未 `read()` 的流式 `response.text`），并把状态码与截断后的正文展示给用户。

#### Scenario: 成功流式输出

- **WHEN** 端点可达并返回 SSE token 流
- **THEN** 客户端按顺序产出 token，直到流结束

#### Scenario: 服务不可达

- **WHEN** `MAX_PROVIDER=local` 且配置的 `base_url` 拒绝连接
- **THEN** 客户端抛出已处理错误，TUI 展示该错误并提示建议的 `max-gui serve` 命令

#### Scenario: 流式 HTTP 错误可读

- **WHEN** 流式 `/chat/completions` 返回非 2xx
- **THEN** 用户可见错误包含该状态码，且 MUST NOT 出现 `without having called read()`

### Requirement: 模型选择

`MAX_PROVIDER=local` 时，系统 SHALL 默认使用完整目录名 `qwen3.5-4b`，权重路径为 `model/qwen3.5-4b`。请求中的 `model` MUST 等于 `MODEL_NAME` 原文。系统 MUST NOT 接受 `2b`、`4b`、`9b`、`qwen2b`、`qwen4b`、`qwen9b` 等短别名。本地权重缺失 MUST 报告包含该目录路径的错误，MUST NOT 提及 `max-gui download`。自动化测试 MUST 仍可显式钉死 `qwen3.5-2b` 占位权重，不得依赖本机 4B 目录。运行时模型 MUST 只来自配置中的 `MODEL_NAME`，MUST NOT 提供 TUI `/model` 或 CLI `--model`。

#### Scenario: 默认模型

- **WHEN** `MAX_PROVIDER=local` 且未设置 `MODEL_NAME`
- **THEN** 请求使用 model id `qwen3.5-4b`，权重目录为 `model/qwen3.5-4b`

#### Scenario: 短别名拒绝

- **WHEN** `MAX_PROVIDER=local` 且 `MODEL_NAME=4b`
- **THEN** 系统拒绝该配置或在缺目录 `model/4b` 时失败，且 MUST NOT 将其解释为 `qwen3.5-4b`

#### Scenario: 权重缺失

- **WHEN** 所选 `MODEL_NAME` 没有完整的本地权重目录
- **THEN** 系统报告包含 `model/<MODEL_NAME>` 路径的错误，且不发送请求，且不含 download 命令

### Requirement: serve 与 download 辅助命令

CLI SHALL 提供 `max-gui serve`，仅当 `MAX_PROVIDER=local` 时以 OpenAI 兼容模式启动 vLLM，并带上配置的 `--max-model-len`、`--gpu-memory-utilization`、`--dtype`。开发默认加载 `model/qwen3.5-4b`。vLLM 可执行文件 MUST 按 `MAX_GUI_VLLM`、`PATH` 中的 `vllm`、`~/.venv-vllm-metal/bin/vllm` 的顺序解析，MUST NOT 回退到当前解释器的 `python -m vllm`。找不到可执行文件时 MUST 以非零退出码报中文错误。`MAX_PROVIDER=modelscope` 时 `max-gui serve` MUST 以非零退出码失败并提示修改 `.env`。CLI MUST NOT 提供 `max-gui download` 子命令。

#### Scenario: 启动已配置模型

- **WHEN** `MAX_PROVIDER=local`，用户执行 `max-gui serve` 且权重存在，并且能解析到 vLLM 可执行文件
- **THEN** 使用该二进制以配置的模型路径启动 OpenAI 兼容 HTTP API，并开启 `--enable-auto-tool-choice` 与 `--tool-call-parser qwen3_coder`；未指定 `MODEL_NAME` 时路径为 `model/qwen3.5-4b`

#### Scenario: modelscope 下拒绝 serve

- **WHEN** `MAX_PROVIDER=modelscope` 且用户执行 `max-gui serve`
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
