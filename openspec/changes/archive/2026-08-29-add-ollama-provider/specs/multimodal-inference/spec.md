## ADDED Requirements

### Requirement: Ollama OpenAI 兼容请求

系统 MUST 让 `ollama` provider 复用现有 OpenAI 兼容 `/chat/completions` 请求、消息编码、SSE 解析、工具调用与 token 用量链路。请求 MUST 使用注册表中的模型与端点，且 MUST NOT 发送 `Authorization` 头。连接失败 MUST 提示检查 WSL Ollama 服务、Windows 防火墙与局域网端口，且 MUST NOT 提示运行 `max-gui serve`。

#### Scenario: Ollama 请求带工具 schema

- **WHEN** `MAX_PROVIDER=ollama` 且 Agent 提供桌面工具 schema
- **THEN** POST `http://192.168.1.158:11434/v1/chat/completions` 的 JSON 使用模型 `qwen3.5:9b`，包含 `tools` 与 `tool_choice=auto`，且没有 `Authorization` 头

#### Scenario: Ollama 服务不可达

- **WHEN** `MAX_PROVIDER=ollama` 的端点拒绝连接
- **THEN** 系统报告 WSL Ollama、Windows 防火墙和局域网端口的中文检查提示，且不提示 `max-gui serve`
