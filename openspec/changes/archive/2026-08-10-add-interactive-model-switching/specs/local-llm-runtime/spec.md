## MODIFIED Requirements

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
- **WHEN** a loaded selected runtime fails while generating a response
- **THEN** the chat displays the failed generation state and remains interactive without desktop control or network access
