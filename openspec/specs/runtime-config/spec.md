# runtime-config Specification

## Purpose

仓库根目录 `.env` 作为可调运行参数的单一来源：推理后端、密钥、模型名与既有 `MAX_GUI_*` 字段。
## Requirements
### Requirement: 仓库根目录 .env 为可调配置来源

系统 MUST 在解析运行配置时，于探测到的仓库根目录读取 `.env`（若存在）。载入 MUST 使用不覆盖已有进程环境变量的方式，以便测试与显式 export 优先。根目录无 `.env` 时 MUST 使用代码内缺省值，且 MUST NOT 因此失败。仓库 MUST 提供无密钥的 `.env.example`。`.env` MUST NOT 作为受版本管理的密钥文件提交。主推理 provider 的 `.env` 配置 MUST 只负责选择名称和保存 provider 专属密钥；模型、端点与能力 MUST 由 Python provider 定义提供。

#### Scenario: 从 .env 读取 provider

- **WHEN** 仓库根存在 `.env` 且含 `MAX_PROVIDER=modelscope`，进程未设置该变量
- **THEN** 加载后的配置 `provider` 为 `modelscope`

#### Scenario: 进程环境优先于 .env

- **WHEN** 进程已设置 `MAX_PROVIDER=local`，且 `.env` 写有 `MAX_PROVIDER=modelscope`
- **THEN** 加载后的配置 `provider` 为 `local`

#### Scenario: 无 .env 文件

- **WHEN** 仓库根不存在 `.env`
- **THEN** 配置使用代码内缺省 `provider=local`、模型与端点，启动不因缺文件失败

### Requirement: 推理相关键名与缺省

系统 MUST 识别 `MAX_PROVIDER`（仅 `local`、`remote`、`modelscope`、`dashscope` 或 `openrouter`，缺省 `local`）、`MAX_MODELSCOPE_KEY`、`MAX_DASHSCOPE_KEY` 与 `MAX_OPENROUTER_KEY`。未知 `MAX_PROVIDER` 值 MUST 拒绝并给出中文错误。系统 MUST NOT 将 `MAX_PROVIDER_KEY`、`MODELSCOPE_SDK_TOKEN`、`DASHSCOPE_API_KEY` 或 `OPENROUTER_API_KEY` 当作推理密钥。每个后端请求中的 `model` 与 `base_url` MUST 来自 Python provider 定义，`MODEL_NAME`、`MAX_GUI_BASE_URL` 与 `MAX_DASHSCOPE_WORKSPACE` MUST NOT 覆盖主推理 provider 定义。既有可调字段 `MAX_GUI_MAX_ITERATIONS`、`MAX_GUI_MAX_IMAGE_EDGE`、`MAX_GUI_MAX_IMAGE_BYTES`、`MAX_GUI_TOOL_TIMEOUT`、`MAX_GUI_MAX_MODEL_LEN`、`MAX_GUI_GPU_MEM`、`MAX_GUI_DTYPE`、`MAX_GUI_WORKSPACE`、`MAX_GUI_OCR_*` 与 `MAX_GUI_OMNIPARSER_*` MUST 仍可从同一 `.env` 读取。

#### Scenario: local 使用代码内定义

- **WHEN** `MAX_PROVIDER` 未设置或为 `local`
- **THEN** 配置中的模型为 `qwen3.5-4b`，根端点为 `http://127.0.0.1:8000/v1`

#### Scenario: remote 使用代码内定义

- **WHEN** `MAX_PROVIDER=remote`
- **THEN** 配置中的模型为 `qwen3.5-4b`，根端点为 `http://192.168.1.158:8000/v1`

#### Scenario: modelscope 使用专属密钥

- **WHEN** `MAX_PROVIDER=modelscope` 且 `MAX_MODELSCOPE_KEY=ms-token`
- **THEN** 配置使用模型 `Qwen/Qwen3.8-27B`、魔搭固定端点与密钥 `ms-token`

#### Scenario: dashscope 使用专属密钥

- **WHEN** `MAX_PROVIDER=dashscope` 且 `MAX_DASHSCOPE_KEY=sk-token`
- **THEN** 配置使用模型 `qwen3.8-27b`、代码内北京专属端点与密钥 `sk-token`

#### Scenario: openrouter 使用代码内默认值

- **WHEN** `MAX_PROVIDER=openrouter` 且 `MAX_OPENROUTER_KEY=or-token`
- **THEN** 配置使用模型 `qwen/qwen3.5-plus`、根端点 `https://openrouter.ai/api/v1` 与密钥 `or-token`

#### Scenario: 非法 provider

- **WHEN** `MAX_PROVIDER` 为 `openai` 或其它未注册值
- **THEN** 加载配置失败，错误信息为中文且不启动 TUI

#### Scenario: 旧共享键不再生效

- **WHEN** `MAX_PROVIDER=openrouter` 且仅设置 `MAX_PROVIDER_KEY`、未设置 `MAX_OPENROUTER_KEY`
- **THEN** 系统视为缺少 OpenRouter 密钥

### Requirement: OmniParser 路径 worker 必须为同机地址

当 OmniParser worker 协议使用主进程本地绝对图像路径时，`MAX_GUI_OMNIPARSER_BASE_URL` 的 host MUST 为 loopback 地址。配置为非 loopback 地址时，首次 `locate` MUST 返回中文配置错误，MUST NOT 将本地绝对路径发送到该地址，也 MUST NOT 启动新的 worker。

#### Scenario: 拒绝远端路径 worker

- **WHEN** `MAX_GUI_OMNIPARSER_BASE_URL` 配置为 `http://192.0.2.10:8002`
- **THEN** `locate` 返回说明仅支持本机 worker 的中文错误，且不会发出 HTTP 请求

### Requirement: Provider 定义集中在 Python 注册表

系统 MUST 在独立 Python provider 模块中集中定义全部主推理 provider。每个定义 MUST 包含唯一名称、默认模型、OpenAI 兼容根端点、密钥环境变量名或无密钥标记、本地权重检查能力、`serve` 能力和历史思考回传能力。配置、客户端、CLI 与生命周期代码 MUST 读取这些定义，MUST NOT 各自维护 provider 名单或云端/密钥集合。

#### Scenario: provider 名单来自单一注册表

- **WHEN** 系统解析 `MAX_PROVIDER` 或生成非法 provider 的允许值提示
- **THEN** 名单来自独立 provider 注册表，且包含 `local`、`remote`、`modelscope`、`dashscope` 与 `openrouter`

#### Scenario: 切换时只改 provider 名称

- **WHEN** `.env` 已同时保存各云端 provider 的专属密钥
- **THEN** 用户只修改 `MAX_PROVIDER` 即可选择对应模型、端点与密钥
