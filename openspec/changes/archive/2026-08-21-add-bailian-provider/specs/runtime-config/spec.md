## ADDED Requirements

### Requirement: bailian 业务空间

`MAX_PROVIDER=bailian` 时，系统 MUST 读取 `MAX_BAILIAN_WORKSPACE`（业务空间 ID），去空白后 MUST 非空。该值 MUST 用于拼出北京专属推理域名，MUST NOT 写入会话 JSON。空值 MUST 在启动 TUI 或首次请求前以中文报错，MUST NOT 提示 `max-gui serve`。`local` 与 `modelscope` MUST NOT 要求该键。

#### Scenario: bailian 读取 Workspace

- **WHEN** `MAX_PROVIDER=bailian` 且 `MAX_BAILIAN_WORKSPACE=llm-demo`
- **THEN** 配置中的业务空间 ID 为 `llm-demo`

#### Scenario: bailian 缺 Workspace

- **WHEN** `MAX_PROVIDER=bailian` 且未设置或仅空白 `MAX_BAILIAN_WORKSPACE`
- **THEN** 系统报告中文缺业务空间错误，不提示 `max-gui serve`

#### Scenario: local 不要求 Workspace

- **WHEN** `MAX_PROVIDER=local` 且未设置 `MAX_BAILIAN_WORKSPACE`
- **THEN** 配置加载成功，不因缺业务空间失败

## MODIFIED Requirements

### Requirement: 推理相关键名与缺省

系统 MUST 识别 `MAX_PROVIDER`（仅 `local`、`modelscope` 或 `bailian`，缺省 `local`）、`MAX_PROVIDER_KEY`、`MODEL_NAME`、`MAX_BAILIAN_WORKSPACE`。未知 `MAX_PROVIDER` 值 MUST 拒绝并给出中文错误。系统 MUST NOT 将 `MODELSCOPE_SDK_TOKEN` 或 `DASHSCOPE_API_KEY` 当作推理密钥。`local` 下未设置 `MODEL_NAME` 时 MUST 默认为 `qwen3.5-4b`。`modelscope` 下未设置 `MODEL_NAME` 时 MUST 默认为 `Qwen/Qwen3.8-27B`。`bailian` 下未设置 `MODEL_NAME` 时 MUST 默认为 `qwen3.8-27b`。既有可调字段 `MAX_GUI_BASE_URL`、`MAX_GUI_MAX_ITERATIONS`、`MAX_GUI_MAX_IMAGE_EDGE`、`MAX_GUI_MAX_IMAGE_BYTES`、`MAX_GUI_TOOL_TIMEOUT`、`MAX_GUI_MAX_MODEL_LEN`、`MAX_GUI_GPU_MEM`、`MAX_GUI_DTYPE`、`MAX_GUI_WORKSPACE`、`MAX_GUI_OCR_*` MUST 仍可从同一 `.env` 读取。

#### Scenario: local 默认模型名

- **WHEN** `MAX_PROVIDER` 未设置或为 `local`，且未设置 `MODEL_NAME`
- **THEN** 配置中的模型名为 `qwen3.5-4b`

#### Scenario: modelscope 默认模型名

- **WHEN** `MAX_PROVIDER=modelscope` 且未设置 `MODEL_NAME`
- **THEN** 配置中的模型名为 `Qwen/Qwen3.8-27B`

#### Scenario: bailian 默认模型名

- **WHEN** `MAX_PROVIDER=bailian` 且未设置 `MODEL_NAME`
- **THEN** 配置中的模型名为 `qwen3.8-27b`

#### Scenario: 非法 provider

- **WHEN** `MAX_PROVIDER` 为 `openai` 或其它非 `local` / `modelscope` / `bailian` 的值
- **THEN** 加载配置失败，错误信息为中文且不启动 TUI

#### Scenario: 不认 SDK Token 环境变量

- **WHEN** 仅设置 `MODELSCOPE_SDK_TOKEN` 而未设置 `MAX_PROVIDER_KEY`，且 `MAX_PROVIDER=modelscope`
- **THEN** 系统视为缺少推理密钥

#### Scenario: 不认 DASHSCOPE_API_KEY

- **WHEN** 仅设置 `DASHSCOPE_API_KEY` 而未设置 `MAX_PROVIDER_KEY`，且 `MAX_PROVIDER=bailian`
- **THEN** 系统视为缺少推理密钥
