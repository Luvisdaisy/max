## Context

当前 provider 注册表已集中定义本机、可信局域网网关和云端 OpenAI 兼容服务。用户的 WSL Ollama 在 `192.168.1.158:11434` 暴露 `/v1/chat/completions`，模型为 `qwen3.5:9b`，不要求 API Key。实测时该端口拒绝连接，因此实现不能把本次网络可用性当作已验证事实。

## Goals / Non-Goals

**Goals:**

- 以最小改动让 `MAX_PROVIDER=ollama` 使用固定、无密钥的 OpenAI 兼容配置。
- 沿用现有消息编码、SSE、工具调用、错误处理与 `serve` 限制。
- 给出可直接切换的配置和可自动验证的测试。

**Non-Goals:**

- 不远程启动、停止或重配 WSL / Ollama，也不绕过防火墙。
- 不新增运行时覆盖模型或端点的环境变量。
- 不为 Ollama 实现专属 SDK、动作 JSON 兼容模式或服务健康检查。

## Decisions

- 在 `ProviderDefinition` 注册表新增 `ollama`：模型固定 `qwen3.5:9b`、根端点固定 `http://192.168.1.158:11434/v1`、无认证、不检查 Mac 本地权重、禁止 `max-gui serve`。这样复用现有配置与客户端分支，避免重复配置来源。
- 连接失败沿用 provider 的 `connection_hint`，明确提示 WSL 服务、Windows 防火墙与局域网端口；不把错误提示为本机 vLLM 启动失败。
- 测试使用 `httpx.MockTransport` 验证模型、URL、无 Authorization 头与请求中 tools，不依赖局域网服务的瞬时状态。

## Risks / Trade-offs

- [Ollama 的工具调用或多模态兼容程度依版本和模型而异] → provider 只保证发送标准 OpenAI 兼容请求；真实 Agent 闭环须在服务恢复后单独验收。
- [固定 IP 或模型标签改变] → 修改唯一的注册表定义；不通过环境变量分散覆盖。
- [WSL 服务不可达] → 保留真实连接失败，并在用户文档给出服务监听与防火墙检查方向。

## Migration Plan

1. 更新后在 `.env` 设为 `MAX_PROVIDER=ollama`。
2. 在 Mac 上再次执行最小 `/v1/chat/completions` 请求，再进行 max-gui 的文本和工具调用验收。
3. 回退时把 `MAX_PROVIDER` 改回原值；代码无需数据迁移。
