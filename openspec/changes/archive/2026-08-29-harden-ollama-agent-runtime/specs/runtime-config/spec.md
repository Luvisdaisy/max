## ADDED Requirements

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
