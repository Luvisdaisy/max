## ADDED Requirements

### Requirement: Ollama provider 配置

系统 MUST 识别无密钥的 `MAX_PROVIDER=ollama`。该 provider 的模型与 OpenAI 兼容根端点 MUST 仅来自 Python provider 注册表，分别为 `qwen3.5:9b` 与 `http://192.168.1.158:11434/v1`；系统 MUST NOT 读取 API Key、检查 Mac 本地权重或允许 `max-gui serve`。`.env.example` 与 README MUST 说明该 provider 的名称及用途。

#### Scenario: 选择 Ollama

- **WHEN** `MAX_PROVIDER=ollama`
- **THEN** 加载后的配置使用模型 `qwen3.5:9b`、根端点 `http://192.168.1.158:11434/v1` 与空认证配置

#### Scenario: 已移除 serve 子命令

- **WHEN** `MAX_PROVIDER=ollama` 且用户执行 `max-gui serve`
- **THEN** CLI 将该命令视为不受支持的子命令并以非零退出码失败，且不提示改为 `local`
