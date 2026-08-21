# runtime-config Specification

## Purpose

仓库根目录 `.env` 作为可调运行参数的单一来源：推理后端、密钥、模型名与既有 `MAX_GUI_*` 字段。

## Requirements

### Requirement: 仓库根目录 .env 为可调配置来源

系统 MUST 在解析运行配置时，于探测到的仓库根目录读取 `.env`（若存在）。载入 MUST 使用不覆盖已有进程环境变量的方式，以便测试与显式 export 优先。根目录无 `.env` 时 MUST 使用代码内缺省值，且 MUST NOT 因此失败。仓库 MUST 提供无密钥的 `.env.example`。`.env` MUST NOT 作为受版本管理的密钥文件提交。

#### Scenario: 从 .env 读取 provider

- **WHEN** 仓库根存在 `.env` 且含 `MAX_PROVIDER=modelscope`，进程未设置该变量
- **THEN** 加载后的配置 `provider` 为 `modelscope`

#### Scenario: 进程环境优先于 .env

- **WHEN** 进程已设置 `MAX_PROVIDER=local`，且 `.env` 写有 `MAX_PROVIDER=modelscope`
- **THEN** 加载后的配置 `provider` 为 `local`

#### Scenario: 无 .env 文件

- **WHEN** 仓库根不存在 `.env`
- **THEN** 配置使用缺省 `provider=local` 与缺省 `MODEL_NAME`，启动不因缺文件失败

### Requirement: 推理相关键名与缺省

系统 MUST 识别 `MAX_PROVIDER`（仅 `local` 或 `modelscope`，缺省 `local`）、`MAX_PROVIDER_KEY`、`MODEL_NAME`。未知 `MAX_PROVIDER` 值 MUST 拒绝并给出中文错误。系统 MUST NOT 将 `MODELSCOPE_SDK_TOKEN` 当作推理密钥。`local` 下未设置 `MODEL_NAME` 时 MUST 默认为 `qwen3.5-4b`。`modelscope` 下未设置 `MODEL_NAME` 时 MUST 默认为 `Qwen/Qwen3.8-27B`。既有可调字段 `MAX_GUI_BASE_URL`、`MAX_GUI_MAX_ITERATIONS`、`MAX_GUI_MAX_IMAGE_EDGE`、`MAX_GUI_MAX_IMAGE_BYTES`、`MAX_GUI_TOOL_TIMEOUT`、`MAX_GUI_MAX_MODEL_LEN`、`MAX_GUI_GPU_MEM`、`MAX_GUI_DTYPE`、`MAX_GUI_WORKSPACE`、`MAX_GUI_OCR_*` MUST 仍可从同一 `.env` 读取。

#### Scenario: local 默认模型名

- **WHEN** `MAX_PROVIDER` 未设置或为 `local`，且未设置 `MODEL_NAME`
- **THEN** 配置中的模型名为 `qwen3.5-4b`

#### Scenario: modelscope 默认模型名

- **WHEN** `MAX_PROVIDER=modelscope` 且未设置 `MODEL_NAME`
- **THEN** 配置中的模型名为 `Qwen/Qwen3.8-27B`

#### Scenario: 非法 provider

- **WHEN** `MAX_PROVIDER` 为 `openai` 或其它非 `local`/`modelscope` 的值
- **THEN** 加载配置失败，错误信息为中文且不启动 TUI

#### Scenario: 不认 SDK Token 环境变量

- **WHEN** 仅设置 `MODELSCOPE_SDK_TOKEN` 而未设置 `MAX_PROVIDER_KEY`，且 `MAX_PROVIDER=modelscope`
- **THEN** 系统视为缺少推理密钥
