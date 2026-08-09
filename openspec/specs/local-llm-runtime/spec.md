# local-llm-runtime Specification

## Purpose

提供项目内 Qwen3.5-2B 的离线懒加载文本生成运行时，使 Textual 聊天能给出真实本地回复并在资源受限时保留可诊断边界。

## Requirements

### Requirement: Offline local text generation
The system SHALL generate responses to chat text using only the complete project-local Qwen3.5-2B model. It MUST load the model lazily on the first eligible chat request, use local-only model and processor resolution, and MUST NOT download model files or call a remote inference service. Qwen3.5-4B MUST NOT be required for this capability's development or automated validation.

#### Scenario: First chat request loads the local model
- **WHEN** a developer submits ordinary text in the Textual chat and the complete local Qwen3.5-2B model is available
- **THEN** the system visibly reports loading, generates a local text response, and retains the loaded runtime for later messages in the same session

#### Scenario: Later chat request reuses the runtime
- **WHEN** the local model has already loaded successfully in the current Textual session
- **THEN** a later ordinary text message is generated without a second model load

### Requirement: Local runtime failure boundary
The system SHALL report missing model files, unavailable CUDA/BF16 support, model-load failure, and generation failure as clear in-session errors. A failure MUST leave the Textual session usable for `/doctor` and `/quit`, and MUST NOT trigger network fallback, desktop input, or model download.

#### Scenario: Model cannot load
- **WHEN** the local Qwen3.5-2B model is missing, incomplete, or cannot fit in available GPU memory
- **THEN** the chat displays a local remediation-oriented error and remains interactive without attempting a remote fallback

#### Scenario: Generation fails after loading
- **WHEN** a loaded local runtime fails while generating a response
- **THEN** the chat displays the failed generation state and remains interactive without desktop control or network access
