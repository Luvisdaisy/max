## MODIFIED Requirements

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

### Requirement: 七牛 provider 配置

系统 MUST 支持 `MAX_PROVIDER=qiniu`。其模型 MUST 为 `z-ai/glm-5.3-flash`，OpenAI 兼容
根端点 MUST 为 `https://api.qnaigc.com/v1`，密钥 MUST 只从 `MAX_QINIU_KEY` 读取；
`.env.example` 与 README MUST 说明该 provider、密钥变量与切换方式。

#### Scenario: 仅七牛专属密钥可用

- **WHEN** `MAX_PROVIDER=qiniu`，仅设置 `QINIU_API_KEY` 且 `MAX_QINIU_KEY` 为空
- **THEN** 系统视为缺少密钥，在发起 HTTP 请求前给出包含 `MAX_QINIU_KEY` 的中文错误
