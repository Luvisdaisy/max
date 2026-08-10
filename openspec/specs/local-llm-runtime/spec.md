# local-llm-runtime Specification

## Purpose

提供项目内 Qwen3.5-2B 的离线懒加载文本生成运行时，使 Textual 聊天能给出真实本地回复并在资源受限时保留可诊断边界。

## Requirements

### Requirement: 离线视觉观察解释
本地运行时 SHALL 在已选择模型支持视觉输入时，将调用方提供的内存图像和结构化工具观察用于生成解释。运行时 MUST 使用本地文件和离线模型加载，并 MUST 不持久化、回显或网络传输原始图像。

#### Scenario: 解释内存截图
- **WHEN** 调用方提供内存屏幕图像、任务目标和有效的已选择视觉模型
- **THEN** 运行时生成针对该观察的本地文本解释，并保留原有模型选择与失败边界

#### Scenario: 拒绝缺失视觉输入能力的模型
- **WHEN** 已选择模型或处理器无法接受图像输入
- **THEN** 运行时返回明确的本地视觉能力错误，不调用远程服务且不更改当前模型选择

### Requirement: Offline local text generation
The system SHALL generate responses to chat text using only the complete project-local model selected for the current session. It MUST load the selected model lazily on the first eligible chat request after selection, use local-only model and processor resolution, and MUST NOT download model files or call a remote inference service. A Qwen3.5-4B model MUST NOT be required for this capability's development or automated validation.

#### Scenario: First chat request loads the local model
- **WHEN** a developer submits ordinary text in the Textual chat and the selected complete local model is available
- **THEN** the system visibly reports loading, generates a local text response, and retains the loaded runtime for later messages in the same session until another model is selected

#### Scenario: Later chat request reuses the runtime
- **WHEN** the selected local model has already loaded successfully in the current Textual session
- **THEN** a later ordinary text message is generated without a second model load

#### Scenario: Switching model resets the loaded runtime
- **WHEN** the developer selects a different local model after prior chat activity
- **THEN** the next ordinary text request loads only the newly selected model and does not include the previous model's conversation history

### Requirement: Local runtime failure boundary
The system SHALL report unavailable selection, missing required model files, unavailable CUDA/BF16 support, model-load failure, and generation failure as clear in-session errors. A failure MUST leave the Textual session usable for `/model`, `/doctor`, and `/quit`, MUST preserve the current model selection when loading or generation fails, and MUST NOT trigger network fallback, desktop input, or model download.

#### Scenario: Model cannot load
- **WHEN** the selected local model is incomplete or cannot fit in available GPU memory
- **THEN** the chat displays a local remediation-oriented error and remains interactive without attempting a remote fallback

#### Scenario: Generation fails after loading
- **WHEN** a loaded local runtime fails while generating a response
- **THEN** the chat displays the failed generation state and remains interactive without desktop control or network access
