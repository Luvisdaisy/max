## Context

当前 `config.py` 同时维护 provider 名单、默认模型、端点构造、密钥校验和本地权重规则；`InferenceClient`、CLI、生命周期及消息编码又通过 provider 名称集合或字符串分支重复判断能力。现有五类目标后端均提供 OpenAI 兼容 Chat Completions，因此协议层无需拆成多个客户端，真正需要抽离的是后端定义与能力元数据。

用户要求 `.env` 预存全部云端密钥，日常切换只修改 `MAX_PROVIDER`；模型、端点等非敏感配置直接在 Python 文件中维护。现有 `.env` 中的 remote 地址和 dashscope 专属 Workspace 将迁入 provider 定义，真实密钥仍只保存在被 Git 忽略的 `.env`。

## Goals / Non-Goals

**Goals:**

- 用单一不可变 provider 注册表定义 `local`、`remote`、`modelscope`、`dashscope` 与 `openrouter`
- 所有 provider 共用现有 `/chat/completions` 请求、SSE 解析、多模态编码和工具调用链路
- OpenRouter 使用 `https://openrouter.ai/api/v1` 与默认模型 `qwen/qwen3.5-plus`
- `.env` 同时保存 provider 专属密钥，切换时只改 `MAX_PROVIDER`
- 用能力字段替代散落的 provider 名称集合与分支，并保持中文错误文案

**Non-Goals:**

- OpenAI Auth、ChatGPT/Codex 登录态复用或 OpenAI 原生 provider
- Responses API、OpenRouter SDK、OpenAI SDK 或 provider 专属客户端
- TUI/CLI 动态切换 provider、运行时模型覆盖或自动模型发现
- 改动 OCR、OmniParser、Agent 状态、会话格式和 benchmark 行为

## Decisions

### 1. 使用不可变定义注册表，不建立 provider 类继承树

`src/max_gui/provider.py` 定义 `ProviderDefinition` 与 `PROVIDERS` 映射。每个定义至少包含：名称、默认模型、OpenAI 兼容根端点、密钥环境变量名、本地权重检查、`serve` 许可、历史思考回传和连接失败提示。

注册表只描述差异；`InferenceClient` 仍是唯一网络客户端。相比每个 provider 一个子类，该结构没有重复的 HTTP/SSE 实现，也符合所有后端协议一致的约束。

### 2. provider 非敏感配置由 Python 定义，Settings 保存解析快照

`load_settings` 只从 `MAX_PROVIDER` 选择定义，并把定义中的 `model_name`、`base_url` 与选中密钥解析到 `Settings`。既有调用方仍读取 `Settings.provider`、`model_name`、`base_url` 和 `api_key`，避免把注册表对象写入会话或观测记录。

固定定义如下：

| provider | 模型 | 根端点 | 密钥环境变量 |
|---|---|---|---|
| `local` | `qwen3.5-4b` | `http://127.0.0.1:8000/v1` | 无 |
| `remote` | `qwen3.5-4b` | `http://192.168.1.158:8000/v1` | 无 |
| `modelscope` | `Qwen/Qwen3.8-27B` | `https://api-inference.modelscope.cn/v1` | `MAX_MODELSCOPE_KEY` |
| `dashscope` | `qwen3.8-27b` | `https://llm-xxcxmbwit4rg4ios.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` | `MAX_DASHSCOPE_KEY` |
| `openrouter` | `qwen/qwen3.5-plus` | `https://openrouter.ai/api/v1` | `MAX_OPENROUTER_KEY` |

`MODEL_NAME`、`MAX_GUI_BASE_URL`、`MAX_DASHSCOPE_WORKSPACE` 与共享的 `MAX_PROVIDER_KEY` 不再参与主推理 provider 解析。需要调整模型或端点时修改注册表定义并经过代码评审与测试。

### 3. 密钥值继续在 `.env`，定义只保存变量名

注册表中的 `api_key_env` 只保存环境变量名，真实值由 `load_settings` 从进程环境或 `.env` 读取。三个云端 provider 使用独立键，因此可同时预存密钥；切换 provider 不需要同步覆盖共享键。

不把密钥写入 `provider.py`，也不读取 `MODELSCOPE_SDK_TOKEN`、`DASHSCOPE_API_KEY` 或 `OPENROUTER_API_KEY`，避免同一后端存在多套优先级不清的凭据来源。

### 4. 能力驱动运行分支

客户端根据选中定义的能力完成：

- `requires_local_weights`：仅 `local` 请求前检查权重
- `api_key_env`：非空时校验密钥并发送 Bearer 头
- `replay_reasoning`：仅 `dashscope` 回传历史 `reasoning_content`
- `allows_serve`：仅 `local` 可启动本机 vLLM
- `connection_hint`：网络失败时展示 provider 对应中文提示

`openrouter` 不获得特殊协议分支；它与其它后端一样发送 `stream_options.include_usage`、`tools` 与 `tool_choice=auto`，并使用现有 `reasoning_content` / `reasoning` 解析兼容逻辑。

## Risks / Trade-offs

- [remote 地址和 dashscope Workspace 被固定在源码，环境迁移需要改代码] → 这是用户明确选择的配置模式；集中在单一注册表，并通过测试锁定。
- [删除 `MODEL_NAME` 等覆盖会影响旧 `.env`] → 更新 `.env.example` 与 README，旧键即使残留也明确忽略；迁移只需添加三个专属密钥键。
- [OpenRouter 上游模型可能不支持图像或工具调用] → 默认模型按用户指定固定；用 HTTP 合约测试验证请求形状，真实账户/模型可用性作为外部端到端验证边界单独说明。
- [现有工作区含无关未提交修改] → 仅编辑本变更相关区域，先检查差异并避免覆盖 benchmark 与 cleanup 改动。

## Migration Plan

1. 在 `.env` 中把现有共享密钥复制到对应的 `MAX_MODELSCOPE_KEY` 或 `MAX_DASHSCOPE_KEY`，并按需填写 `MAX_OPENROUTER_KEY`。
2. 保留 `MAX_PROVIDER`；删除或忽略 `MAX_PROVIDER_KEY`、`MODEL_NAME`、`MAX_GUI_BASE_URL` 与 `MAX_DASHSCOPE_WORKSPACE`。
3. 部署代码后通过配置单元测试和 MockTransport 合约测试验证五个 provider。
4. 回滚时恢复旧 `config.py` 分支及旧环境变量；会话与持久化数据无需迁移。

## Open Questions

无。
