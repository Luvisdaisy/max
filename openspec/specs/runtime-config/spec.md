# runtime-config Specification

## Purpose

仓库根目录 `.env` 作为可调运行参数的单一来源：推理后端、密钥、模型名与既有 `MAX_GUI_*` 字段。
## Requirements
### Requirement: 仓库根目录 .env 为可调配置来源

系统 MUST 在解析运行配置时，于探测到的仓库根目录读取 `.env`（若存在）。载入 MUST
使用不覆盖已有进程环境变量的方式，以便测试与显式 export 优先。根目录无 `.env` 时
MUST 使用代码内缺省值，且 MUST NOT 因此失败。仓库 MUST 提供无密钥的 `.env.example`。
`.env` MUST NOT 作为受版本管理的密钥文件提交。主推理 provider 的 `.env` 配置 MUST
只负责选择名称和保存 provider 专属密钥；模型、端点与能力 MUST 由 Python provider
定义提供。

#### Scenario: 从 .env 读取 provider

- **WHEN** 仓库根存在 `.env` 且含 `MAX_PROVIDER=modelscope`，进程未设置该变量
- **THEN** 加载后的配置 `provider` 为 `modelscope`

#### Scenario: 进程环境优先于 .env

- **WHEN** 进程已设置 `MAX_PROVIDER=ollama`，且 `.env` 写有 `MAX_PROVIDER=modelscope`
- **THEN** 加载后的配置 `provider` 为 `ollama`

#### Scenario: 无 .env 文件

- **WHEN** 仓库根不存在 `.env`
- **THEN** 配置使用代码内缺省 `provider=ollama`、模型与端点，启动不因缺文件失败

### Requirement: 推理相关键名与缺省

系统 MUST 识别 `MAX_PROVIDER`（仅 `ollama`、`modelscope`、`dashscope`、`openrouter` 或
`qiniu`，缺省 `ollama`）、`MAX_MODELSCOPE_KEY`、`MAX_DASHSCOPE_KEY`、
`MAX_OPENROUTER_KEY` 与 `MAX_QINIU_KEY`。未知 `MAX_PROVIDER` 值 MUST 拒绝并给出中文错误；
`local` 与 `remote` MUST 视为未知值。系统 MUST NOT 将 `MAX_PROVIDER_KEY`、
`MODELSCOPE_SDK_TOKEN`、`DASHSCOPE_API_KEY`、`OPENROUTER_API_KEY` 或 `QINIU_API_KEY`
当作推理密钥。每个后端请求中的 `model` 与 `base_url` MUST 来自 Python provider 定义，
`MODEL_NAME`、`MAX_GUI_BASE_URL` 与 `MAX_DASHSCOPE_WORKSPACE` MUST NOT 覆盖主推理
provider 定义。既有可调字段 `MAX_GUI_MAX_ITERATIONS`、`MAX_GUI_MAX_IMAGE_EDGE`、
`MAX_GUI_MAX_IMAGE_BYTES`、`MAX_GUI_TOOL_TIMEOUT`、`MAX_GUI_MAX_MODEL_LEN`、
`MAX_GUI_DTYPE`、`MAX_GUI_WORKSPACE`、`MAX_GUI_OCR_*` 与 `MAX_GUI_OMNIPARSER_*` MUST
仍可从同一 `.env` 读取；`MAX_GUI_GPU_MEM` MUST 不再作为主推理配置项。

#### Scenario: Ollama 使用代码内定义

- **WHEN** `MAX_PROVIDER` 未设置或为 `ollama`
- **THEN** 配置中的模型为 `qwen3.5:9b`，根端点为 `http://192.168.1.158:11434/v1`

#### Scenario: 已移除 provider 被拒绝

- **WHEN** `MAX_PROVIDER=local` 或 `MAX_PROVIDER=remote`
- **THEN** 加载配置失败，错误信息为中文且允许值不含这两个名称

#### Scenario: modelscope 使用专属密钥

- **WHEN** `MAX_PROVIDER=modelscope` 且 `MAX_MODELSCOPE_KEY=ms-token`
- **THEN** 配置使用模型 `Qwen/Qwen3.8-27B`、魔搭固定端点与密钥 `ms-token`

#### Scenario: dashscope 使用专属密钥

- **WHEN** `MAX_PROVIDER=dashscope` 且 `MAX_DASHSCOPE_KEY=sk-token`
- **THEN** 配置使用模型 `qwen3.8-27b`、代码内北京专属端点与密钥 `sk-token`

#### Scenario: openrouter 使用代码内默认值

- **WHEN** `MAX_PROVIDER=openrouter` 且 `MAX_OPENROUTER_KEY=or-token`
- **THEN** 配置使用模型 `qwen/qwen3.5-plus`、根端点 `https://openrouter.ai/api/v1` 与密钥 `or-token`

#### Scenario: qiniu 使用代码内默认值

- **WHEN** `MAX_PROVIDER=qiniu` 且 `MAX_QINIU_KEY=qiniu-token`
- **THEN** 配置使用模型 `z-ai/glm-5.3-flash`、根端点 `https://api.qnaigc.com/v1` 与密钥 `qiniu-token`

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

系统 MUST 在独立 Python provider 模块中集中定义全部主推理 provider。每个定义 MUST
包含唯一名称、默认模型、OpenAI 兼容根端点、密钥环境变量名或无密钥标记、历史思考回传能力
和网络失败提示。配置、客户端与 CLI MUST 读取这些定义，MUST NOT 各自维护 provider 名单
或云端/密钥集合。主推理 provider 定义 MUST NOT 包含本地权重检查或 `serve` 能力。

#### Scenario: provider 名单来自单一注册表

- **WHEN** 系统解析 `MAX_PROVIDER` 或生成非法 provider 的允许值提示
- **THEN** 名单来自独立 provider 注册表，且包含 `ollama`、`modelscope`、`dashscope`、`openrouter` 与 `qiniu`，不包含 `local` 或 `remote`

#### Scenario: 切换时只改 provider 名称

- **WHEN** `.env` 已同时保存各云端 provider 的专属密钥
- **THEN** 用户只修改 `MAX_PROVIDER` 即可选择 Ollama 或对应云端 provider 的模型、端点与密钥

### Requirement: Ollama provider 配置

系统 MUST 识别无密钥的 `MAX_PROVIDER=ollama`。该 provider 的模型与 OpenAI 兼容根端点 MUST 仅来自 Python provider 注册表，分别为 `qwen3.5:9b` 与 `http://192.168.1.158:11434/v1`；系统 MUST NOT 读取 API Key、检查 Mac 本地权重或允许 `max-gui serve`。`.env.example` 与 README MUST 说明该 provider 的名称及用途。

#### Scenario: 选择 Ollama

- **WHEN** `MAX_PROVIDER=ollama`
- **THEN** 加载后的配置使用模型 `qwen3.5:9b`、根端点 `http://192.168.1.158:11434/v1` 与空认证配置

#### Scenario: 已移除 serve 子命令

- **WHEN** `MAX_PROVIDER=ollama` 且用户执行 `max-gui serve`
- **THEN** CLI 将该命令视为不受支持的子命令并以非零退出码失败，且不提示改为 `local`

### Requirement: 主推理上下文预算配置

系统 MUST 为主推理配置提供正整数 `context_window`、`max_output_tokens` 与 `context_safety_margin`。`ollama` provider 的 `context_window` MUST 固定为 `262144`，MUST NOT 从 `MAX_GUI_MAX_MODEL_LEN` 推断或覆盖；其它保留云端 provider MUST 在注册表使用保守的 `32768`，同样 MUST NOT 把只服务 OCR vLLM 的 `MAX_GUI_MAX_MODEL_LEN` 当成主推理容量。`MAX_GUI_MAX_OUTPUT_TOKENS` 缺省 MUST 为 `8192`，`MAX_GUI_CONTEXT_SAFETY_MARGIN` 缺省 MUST 为 `4096`。输出预留与安全余量之和大于等于上下文容量时，配置 MUST 中文报错。

#### Scenario: Ollama 使用 256K 上下文

- **WHEN** `MAX_PROVIDER=ollama` 且 `MAX_GUI_MAX_MODEL_LEN=128000`
- **THEN** 加载后的 `context_window` 仍为 `262144`

#### Scenario: 云端 provider 不复用 OCR 模型长度

- **WHEN** `MAX_PROVIDER=modelscope` 且 `MAX_GUI_MAX_MODEL_LEN=32768`
- **THEN** 加载后的 `context_window` 为注册表中的保守值 `32768`，且不因修改 OCR 模型长度而变化

#### Scenario: 非法预留被拒绝

- **WHEN** 输出预留与安全余量之和不小于当前 `context_window`
- **THEN** 配置加载失败并给出中文上下文预算错误

### Requirement: 统一上游思考配置

系统 MUST 识别 `MAX_GUI_ENABLE_THINKING`，并把其解析为 `Settings.enable_thinking`。环境变量
缺失时 MUST 为 `false`；仅不区分大小写的 `true` 与 `false` 为合法值。非法非空值 MUST 在
加载配置时以中文错误拒绝，且 MUST NOT 启动 TUI。`.env.example` 与 README MUST 说明该值控制
上游模型是否生成思考，而不是隐藏已经返回的 reasoning。

#### Scenario: 缺省关闭

- **WHEN** 未设置 `MAX_GUI_ENABLE_THINKING`
- **THEN** `Settings.enable_thinking` 为 `false`

#### Scenario: 显式开启

- **WHEN** `MAX_GUI_ENABLE_THINKING=TrUe`
- **THEN** `Settings.enable_thinking` 为 `true`

#### Scenario: 非法值被拒绝

- **WHEN** `MAX_GUI_ENABLE_THINKING=auto`
- **THEN** 加载配置失败，错误信息为中文且包含该变量名

### Requirement: 七牛 provider 配置

系统 MUST 支持 `MAX_PROVIDER=qiniu`。其模型 MUST 为 `z-ai/glm-5.3-flash`，OpenAI 兼容
根端点 MUST 为 `https://api.qnaigc.com/v1`，密钥 MUST 只从 `MAX_QINIU_KEY` 读取；
`.env.example` 与 README MUST 说明该 provider、密钥变量与切换方式。

#### Scenario: 仅七牛专属密钥可用

- **WHEN** `MAX_PROVIDER=qiniu`，仅设置 `QINIU_API_KEY` 且 `MAX_QINIU_KEY` 为空
- **THEN** 系统视为缺少密钥，在发起 HTTP 请求前给出包含 `MAX_QINIU_KEY` 的中文错误

