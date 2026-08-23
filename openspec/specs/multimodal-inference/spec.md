# multimodal-inference Specification

## Purpose

OpenAI 兼容客户端（本机 vLLM、魔搭 API-Inference 或阿里云百炼）、模型配置、图像编码。

## Requirements

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

### Requirement: 流式思考与正文分通道

客户端解析 SSE `delta` 时 MUST 把思考增量与正文增量分开。思考字段 MUST 识别 `reasoning_content`，若缺失则识别 `reasoning`。思考增量 MUST 累加到独立的 `reasoning` 缓冲，MUST 通过思考回调交给调用方，MUST NOT 并入正文 `text`，MUST NOT 触发正文 token 回调。无思考字段的流 MUST 与现有正文流式行为一致。

#### Scenario: 思考增量不进入正文

- **WHEN** SSE 先推送 `delta.reasoning_content` 再推送 `delta.content`
- **THEN** 拼好的回复中思考文本在 `reasoning`，正文在 `text`，正文回调未收到思考那段字符串

#### Scenario: 无思考字段仍流式正文

- **WHEN** SSE 只包含 `delta.content`
- **THEN** 客户端按顺序产出正文 token，`reasoning` 为空

### Requirement: 多模态消息编码

当用户回合包含图像时，客户端 MUST 把每张图作为 `image_url` 内容部件附加（base64 data URL 或原始 URL）。纯文本回合 MUST 只发送文本部件。

#### Scenario: 文本加图像

- **WHEN** 用户发送文本并附一张 PNG
- **THEN** 请求消息内容包含一个文本部件和一个 `image_url` 部件

#### Scenario: 仅文本

- **WHEN** 用户发送文本且无附件
- **THEN** 请求中不含 `image_url` 部件

### Requirement: 编码时注入系统消息

当调用方提供系统提示时，`to_chat_messages` MUST 把一条 `role=system` 的文本消息放在编码结果最前。若原始消息已经以 `system` 开头，MUST NOT 再插入第二条。未提供系统提示时行为 MUST 与原先一致。

#### Scenario: 带系统提示编码

- **WHEN** 调用方传入非空系统提示与一条用户消息
- **THEN** 编码结果第一条为 `system`，第二条为该用户消息

#### Scenario: 已有 system 不重复

- **WHEN** 原始消息第一条已是 `system` 且调用方仍传入系统提示
- **THEN** 编码结果仍只有一条 `system` 消息

### Requirement: 工具消息中的图像回注

当 tool 或 assistant 消息携带本地图像引用时，客户端 MUST 把**本请求中按出现顺序最靠后的、仍存在的至多一张**图作为 `image_url` 内容部件附加（经现有最长边 / 最大字节预处理）。同一条消息的文本摘要 MUST 作为文本部件保留。更早的图像引用 MUST 改为文本摘要（至少含路径；能得知视图宽高则一并写出），MUST NOT 再附加对应 `image_url`。缺失的图像文件 MUST 跳过且不阻止其余部件编码。纯文本 tool 消息 MUST 仍只发送文本。用户消息中的本地图 MUST 计入上述「最近一张」限额。

#### Scenario: 截图进入下一轮 think

- **WHEN** tool 消息内容包含文本摘要与一张存在的 PNG 路径，且该请求中没有更晚的其它图
- **THEN** 发给模型的该条消息同时包含文本部件和 `image_url` 部件

#### Scenario: 纯文本工具结果

- **WHEN** tool 消息内容是字符串且无图像引用
- **THEN** 请求中该条消息不含 `image_url` 部件

#### Scenario: 截图文件缺失

- **WHEN** tool 消息引用的图像路径不存在
- **THEN** 客户端仍发送文本摘要，且不因缺图失败

#### Scenario: 第二张历史截图不再编码为图像

- **WHEN** 请求中按顺序有两张仍存在的本地截图
- **THEN** 仅最后一张带 `image_url`，较早那张只保留含路径的文本摘要

### Requirement: 图像预处理

系统 MUST 拒绝不支持的类型。超过配置的最大边长或最大编码字节数的图像，MUST 在发给模型前缩放或重压缩。预处理 MUST 报告编码后图像的实际像素宽高。同一套缩放规则 MUST 供桌面截图摘要中的视图尺寸使用，避免摘要宽高与模型看见的图不一致。

#### Scenario: 超大图像

- **WHEN** 用户附加的图像最长边超过配置上限
- **THEN** 客户端发送满足最长边约束的缩小图

#### Scenario: 不支持的类型

- **WHEN** 用户附加非图像文件
- **THEN** 系统拒绝该附件，且不会把该文件发给模型

#### Scenario: 报告编码后尺寸

- **WHEN** 一张边长超过上限的截图被预处理
- **THEN** 调用方能得到编码后的 `width` 与 `height`，且二者与实际发送的 JPEG 像素尺寸一致

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

CLI SHALL 提供 `max-gui serve`，仅当 `MAX_PROVIDER=local` 时以 OpenAI 兼容模式启动 vLLM，并带上配置的 `--max-model-len`、`--gpu-memory-utilization`、`--dtype`。开发默认加载 `model/qwen3.5-4b`。vLLM 可执行文件 MUST 按 `MAX_GUI_VLLM`、`PATH` 中的 `vllm`、`~/.venv-vllm-metal/bin/vllm` 的顺序解析，MUST NOT 回退到当前解释器的 `python -m vllm`。找不到可执行文件时 MUST 以非零退出码报中文错误。`MAX_PROVIDER` 为 `modelscope` 或 `dashscope` 时 `max-gui serve` MUST 以非零退出码失败并提示修改 `.env`。CLI MUST NOT 提供 `max-gui download` 子命令。

#### Scenario: 启动已配置模型

- **WHEN** `MAX_PROVIDER=local`，用户执行 `max-gui serve` 且权重存在，并且能解析到 vLLM 可执行文件
- **THEN** 使用该二进制以配置的模型路径启动 OpenAI 兼容 HTTP API，并开启 `--enable-auto-tool-choice` 与 `--tool-call-parser qwen3_coder`；未指定 `MODEL_NAME` 时路径为 `model/qwen3.5-4b`

#### Scenario: modelscope 下拒绝 serve

- **WHEN** `MAX_PROVIDER=modelscope` 且用户执行 `max-gui serve`
- **THEN** 命令以非零退出码失败，错误信息提示将 `MAX_PROVIDER` 改为 `local`

#### Scenario: dashscope 下拒绝 serve

- **WHEN** `MAX_PROVIDER=dashscope` 且用户执行 `max-gui serve`
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

系统 MUST 根据 `MAX_PROVIDER` 选择后端。`local` MUST 使用可配置的本机 OpenAI 兼容端点（缺省 `http://127.0.0.1:8000/v1`），并在发请求前确认 `model/<MODEL_NAME>` 权重完整。`modelscope` MUST 使用 `https://api-inference.modelscope.cn/v1`，MUST 将请求中的 `model` 设为 `MODEL_NAME` 原文，MUST NOT 检查本地权重目录。`modelscope` 且 `MAX_PROVIDER_KEY` 为空时，MUST 在启动 TUI 或首次请求前以中文报错，MUST NOT 提示 `max-gui serve`。`dashscope` MUST 使用 `https://{MAX_DASHSCOPE_WORKSPACE}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`，MUST 将请求中的 `model` 设为 `MODEL_NAME` 原文，MUST NOT 检查本地权重目录。`dashscope` 且 `MAX_PROVIDER_KEY` 为空时，MUST 在启动 TUI 或首次请求前以中文报错，MUST NOT 提示 `max-gui serve`。三种后端 MUST 共用同一套消息编码与流式解析（`dashscope` 的思考回传除外），MUST NOT 为云端省略 `tools`。

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

#### Scenario: dashscope 使用北京专属域名

- **WHEN** `MAX_PROVIDER=dashscope`、`MAX_DASHSCOPE_WORKSPACE=llm-demo`、`MAX_PROVIDER_KEY` 非空
- **THEN** 客户端向 `https://llm-demo.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions` 发请求，`model` 为当前 `MODEL_NAME`，且不检查 `model/qwen3.8-27b`

#### Scenario: dashscope 缺密钥

- **WHEN** `MAX_PROVIDER=dashscope` 且 `MAX_PROVIDER_KEY` 为空
- **THEN** 系统报告中文缺密钥错误，不提示 `max-gui serve`，不发起 HTTP 请求

#### Scenario: dashscope 连接失败不提 serve

- **WHEN** `MAX_PROVIDER=dashscope` 且百炼端点拒绝连接
- **THEN** 用户可见错误不包含 `max-gui serve`

### Requirement: 云端与本地均发送工具 schema

当 Agent 调用推理且工具注册表非空时，客户端 MUST 在请求中包含 `tools` 与 `tool_choice=auto`，无论 `MAX_PROVIDER` 为 `local`、`modelscope` 还是 `dashscope`。解析 SSE 时 MUST 按现有规则拼装 `tool_calls`。系统 MUST NOT 因云端后端而改为从正文 JSON 解析工具调用。

#### Scenario: modelscope 请求带 tools

- **WHEN** `MAX_PROVIDER=modelscope` 且注册表含桌面工具 schema
- **THEN** POST `/chat/completions` 的 JSON 含 `tools` 数组与 `tool_choice` 为 `auto`

#### Scenario: dashscope 请求带 tools

- **WHEN** `MAX_PROVIDER=dashscope` 且注册表含桌面工具 schema
- **THEN** POST `/chat/completions` 的 JSON 含 `tools` 数组与 `tool_choice` 为 `auto`

#### Scenario: 云端流式 tool_calls 拼装

- **WHEN** 魔搭或百炼兼容 SSE 推送带 `index` 的 `delta.tool_calls` 增量
- **THEN** 客户端产出的完整回复含拼好的 `tool_calls`，可供 Agent `act` 使用

### Requirement: dashscope 回传思考字段

当 `MAX_PROVIDER=dashscope` 且助手消息 content 含非空 `reasoning` 时，`to_chat_messages` MUST 在该条请求消息上设置独立字段 `reasoning_content`，其值等于已存思考文本；`content` MUST 仍为正文，MUST NOT 把思考拼进 `content`。无思考的助手消息 MUST NOT 带 `reasoning_content`。`local` 与 `modelscope` MUST 仍不把思考编进请求。

#### Scenario: dashscope 助手带 reasoning_content

- **WHEN** `MAX_PROVIDER=dashscope`，助手 content 为 `{text: "你好", reasoning: "先问候"}`
- **THEN** 编码结果该条含 `content` 为 `你好`，且 `reasoning_content` 为 `先问候`

#### Scenario: dashscope 无思考不加字段

- **WHEN** `MAX_PROVIDER=dashscope`，助手 content 仅有 `text`、无 `reasoning`
- **THEN** 编码结果该条不含 `reasoning_content`

#### Scenario: local 仍不回传思考

- **WHEN** `MAX_PROVIDER=local`，助手 content 含 `reasoning`
- **THEN** 编码结果该条无 `reasoning_content`，`content` 仅为正文

### Requirement: 流式补全回传 token 用量

客户端在 `stream` 为真的 `/chat/completions` 请求中 MUST 发送 `stream_options.include_usage` 为真。解析 SSE 时 MUST 读取 payload 级 `usage`（含 `choices` 为空的用量块），并从中取出 `prompt_tokens`、`completion_tokens`、`total_tokens`。用量块 MUST NOT 触发正文或思考 token 回调，MUST NOT 把空 `choices` 当成补全失败。`total_tokens` 缺失但输入与输出均存在时，合计 MUST 等于二者之和。整段流没有可用 `usage` 时，完整回复 MUST 将用量标为未知，MUST NOT 写成 0。提供方忽略 `stream_options` 时 MUST 仍能完成流式正文与工具调用拼装。

#### Scenario: 空 choices 用量块被采纳

- **WHEN** SSE 在正文增量之后推送一块 `choices` 为空且含 `usage.prompt_tokens`、`usage.completion_tokens`、`usage.total_tokens` 的数据
- **THEN** 拼好的回复带有对应三项用量，且正文与思考回调未因该块被再次调用

#### Scenario: 未回传用量则为未知

- **WHEN** 整个 SSE 流只有带 `delta.content` 的块，没有任何 `usage`
- **THEN** 拼好的回复用量为未知，且正文仍按顺序产出

#### Scenario: 请求带 include_usage

- **WHEN** 客户端发起流式 `/chat/completions`
- **THEN** JSON 请求体含 `stream` 为真，且 `stream_options.include_usage` 为真
