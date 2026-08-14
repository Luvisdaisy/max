# multimodal-inference Specification

## Purpose

vLLM OpenAI 兼容客户端、Qwen VL 模型配置、图像编码。

## Requirements

### Requirement: OpenAI 兼容客户端

系统 SHALL 调用可配置的 OpenAI 兼容 Chat Completions 端点（vLLM）。客户端 MUST 按配置发送 `model`、`messages`、`stream`。连接失败 MUST 作为用户可见错误报告，且 MUST NOT 让 TUI 崩溃。流式请求遇到 HTTP 非 2xx 时，客户端 MUST 读取响应正文（不得访问未 `read()` 的流式 `response.text`），并把状态码与截断后的正文展示给用户。

#### Scenario: 成功流式输出

- **WHEN** 端点可达并返回 SSE token 流
- **THEN** 客户端按顺序产出 token，直到流结束

#### Scenario: 服务不可达

- **WHEN** 配置的 `base_url` 拒绝连接
- **THEN** 客户端抛出已处理错误，TUI 展示该错误并提示建议的 `max-gui serve` 命令

#### Scenario: 流式 HTTP 错误可读

- **WHEN** 流式 `/chat/completions` 返回非 2xx
- **THEN** 用户可见错误包含该状态码，且 MUST NOT 出现 `without having called read()`

### Requirement: 多模态消息编码

当用户回合包含图像时，客户端 MUST 把每张图作为 `image_url` 内容部件附加（base64 data URL 或原始 URL）。纯文本回合 MUST 只发送文本部件。

#### Scenario: 文本加图像

- **WHEN** 用户发送文本并附一张 PNG
- **THEN** 请求消息内容包含一个文本部件和一个 `image_url` 部件

#### Scenario: 仅文本

- **WHEN** 用户发送文本且无附件
- **THEN** 请求中不含 `image_url` 部件

### Requirement: 工具消息中的图像回注

当 tool 或 assistant 消息携带本地图像引用时，客户端 MUST 把每张仍存在的图作为 `image_url` 内容部件附加（经现有最长边 / 最大字节预处理）。同一条消息的文本摘要 MUST 作为文本部件保留。缺失的图像文件 MUST 跳过且不阻止其余部件编码。纯文本 tool 消息 MUST 仍只发送文本。

#### Scenario: 截图进入下一轮 think

- **WHEN** tool 消息内容包含文本摘要与一张存在的 PNG 路径
- **THEN** 发给模型的该条消息同时包含文本部件和 `image_url` 部件

#### Scenario: 纯文本工具结果

- **WHEN** tool 消息内容是字符串且无图像引用
- **THEN** 请求中该条消息不含 `image_url` 部件

#### Scenario: 截图文件缺失

- **WHEN** tool 消息引用的图像路径不存在
- **THEN** 客户端仍发送文本摘要，且不因缺图失败

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

系统 SHALL 默认使用 Qwen3.5-4B 别名（`qwen3.5-4b`，亦可写作 `qwen4b` / `4b`），权重路径为已下载的 `model/qwen3.5-4b`。MUST 允许通过配置或 `/model` 切换到 2B、9B 别名。未知别名 MUST 被拒绝。本地权重缺失 MUST 产生包含该别名 `max-gui download` 命令的错误。自动化测试 MUST 仍可显式钉死 2B 占位权重，不得依赖本机 4B 目录。

#### Scenario: 默认模型

- **WHEN** 未设置模型覆盖
- **THEN** 请求使用 Qwen3.5-4B 配置的 model id，权重目录为 `model/qwen3.5-4b`

#### Scenario: 切换模型

- **WHEN** 用户执行 `/model qwen3.5-2b` 且该别名存在
- **THEN** 后续请求使用 2B 的 model id

#### Scenario: 权重缺失

- **WHEN** 所选别名没有本地目录
- **THEN** 系统报告包含 download 命令的错误，且不发送请求

### Requirement: serve 与 download 辅助命令

CLI SHALL 提供 `max-gui serve`，以 OpenAI 兼容模式启动 vLLM，并带上配置的 `--max-model-len`、`--gpu-memory-utilization`、`--dtype`。开发默认加载 `model/qwen3.5-4b`。vLLM 可执行文件 MUST 按 `MAX_GUI_VLLM`、`PATH` 中的 `vllm`、`~/.venv-vllm-metal/bin/vllm` 的顺序解析，MUST NOT 回退到当前解释器的 `python -m vllm`。找不到可执行文件时 MUST 以非零退出码报中文错误。CLI SHALL 提供 `max-gui download`，经 ModelScope 将所选别名下载到 `model/<alias>`。

#### Scenario: 下载默认模型

- **WHEN** 用户执行不带别名的 `max-gui download`
- **THEN** ModelScope 将默认 4B 模型下载到 `model/qwen3.5-4b`

#### Scenario: 启动已配置模型

- **WHEN** 用户执行 `max-gui serve` 且权重存在，并且能解析到 vLLM 可执行文件
- **THEN** 使用该二进制以配置的模型路径启动 OpenAI 兼容 HTTP API，并开启 `--enable-auto-tool-choice` 与 `--tool-call-parser qwen3_coder`；未指定时路径为 `model/qwen3.5-4b`

#### Scenario: 未激活独立 vLLM 环境

- **WHEN** PATH 中没有 `vllm`，但 `~/.venv-vllm-metal/bin/vllm` 存在
- **THEN** `max-gui serve` 仍使用该默认路径启动，而不是项目 `.venv` 的 Python

#### Scenario: 找不到 vLLM

- **WHEN** `MAX_GUI_VLLM`、PATH 与默认路径都没有可用的 vLLM 可执行文件
- **THEN** 命令以非零退出码失败，错误信息提示 `source ~/.venv-vllm-metal/bin/activate` 或设置 `MAX_GUI_VLLM`
