# multimodal-inference Specification

## Purpose

OpenAI 兼容客户端（本机 vLLM、魔搭 API-Inference 或阿里云百炼）、模型配置、图像编码。
## Requirements
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

### Requirement: Ollama OpenAI 兼容请求

系统 MUST 让 `ollama` provider 复用现有 OpenAI 兼容 `/chat/completions` 请求、消息编码、SSE 解析、工具调用与 token 用量链路。请求 MUST 使用注册表中的模型与端点，且 MUST NOT 发送 `Authorization` 头。连接失败 MUST 提示检查 WSL Ollama 服务、Windows 防火墙与局域网端口，且 MUST NOT 提示运行 `max-gui serve`。

#### Scenario: Ollama 请求带工具 schema

- **WHEN** `MAX_PROVIDER=ollama` 且 Agent 提供桌面工具 schema
- **THEN** POST `http://192.168.1.158:11434/v1/chat/completions` 的 JSON 使用模型 `qwen3.5:9b`，包含 `tools` 与 `tool_choice=auto`，且没有 `Authorization` 头

#### Scenario: Ollama 服务不可达

- **WHEN** `MAX_PROVIDER=ollama` 的端点拒绝连接
- **THEN** 系统报告 WSL Ollama、Windows 防火墙和局域网端口的中文检查提示，且不提示 `max-gui serve`

### Requirement: 推理请求按 token 预算选择上下文

系统 MUST 在发送主推理请求前，按配置的上下文容量扣除输出预留、安全余量和唯一内联图片预留，并对 system、当前用户消息、动态工具 schema 与完整工具调用链进行保守 token 估算。工具调用链 MUST 从最近向前选择，MUST NOT 拆开 assistant `tool_calls` 与对应 tool 消息。当前用户消息、system 与工具 schema 已超过可用预算时 MUST 在网络请求前失败，并给出中文预算诊断。请求 MUST 发送 `max_tokens` 等于配置的输出预留。

#### Scenario: 256K Ollama 请求保留输出空间

- **WHEN** Ollama 上下文容量为 `262144`、输出预留为 `8192`、安全余量为 `4096`
- **THEN** 模型输入选择器不会使用这两项预留，且请求 JSON 的 `max_tokens` 为 `8192`

#### Scenario: 较早完整链被预算裁剪

- **WHEN** 当前用户消息和最近工具链可放入预算，但再加入更早的一条完整链会超限
- **THEN** 请求包含最近完整链，不包含更早完整链，且没有孤立 tool 消息

#### Scenario: 基础请求已超预算

- **WHEN** system、当前用户消息、工具 schema 与图片预留已经超过可用上下文
- **THEN** 客户端不发送 HTTP 请求，并报告容量、预留和估算输入的中文错误

### Requirement: 上下文预算诊断不保存敏感内容

模型调用事件 MUST 记录上下文容量、输出预留、安全余量、估算输入 token、动态工具数量、纳入和裁剪的工具链数量。事件 MUST NOT 复制消息正文、工具 schema、图片内容、键盘输入或完成证据原文。

#### Scenario: 模型事件记录预算计数

- **WHEN** 一次请求从四条完整工具链中按预算选择最近三条
- **THEN** `model.started` 或 `model.completed` 记录纳入三条、裁剪一条及预算数值，且不含工具结果正文

