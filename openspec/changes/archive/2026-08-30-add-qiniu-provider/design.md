## Context

主推理 provider 已由 `src/max_gui/provider.py` 的不可变注册表统一描述；配置加载、
HTTP 客户端、消息编码和错误提示都从该定义获取差异。七牛 AI Token API 提供 OpenAI
兼容的 `/v1/chat/completions` 接口，因此不需要另建 SDK 或客户端。

## Goals / Non-Goals

**Goals:**

- 注册 `qiniu`，将端点、模型、认证变量、上下文预算和中文连接提示集中在既有注册表。
- 固定默认模型为用户确认的 `z-ai/glm-5.3-flash`，根端点为
  `https://api.qnaigc.com/v1`，密钥仅从 `MAX_QINIU_KEY` 读取。
- 复用现有 HTTP、SSE、多模态与工具调用路径，并用 MockTransport 测试锁定请求契约。

**Non-Goals:**

- 不提供模型或端点的运行时覆盖，不调用 `/v1/models` 自动选型。
- 不引入七牛 SDK、Anthropic 协议或供应商专属请求参数。
- 不声称已完成真实账号、视觉输入或工具调用端到端验证。

## Decisions

### 1. 作为统一 OpenAI 兼容 provider，而非新增客户端

注册表新增一项 `qiniu`：模型 `z-ai/glm-5.3-flash`、根端点
`https://api.qnaigc.com/v1`、密钥变量 `MAX_QINIU_KEY`、保守上下文窗口 `32768`、不回传
`reasoning_content`。现有 `InferenceClient` 已负责 `/chat/completions`、SSE 与工具 schema，
直接复用可保持全部 provider 的请求格式一致。

备选方案是七牛专属 SDK 或新客户端；它会重复流式解析与工具调用逻辑，且与接口兼容性不符，
因此不采用。

### 2. 专属环境变量与请求前校验

密钥值只由 `MAX_QINIU_KEY` 注入 `.env` 或进程环境；注册表只保存变量名。配置加载后沿用
`require_provider_key` 在首次请求前校验，成功请求使用 `Authorization: Bearer <key>`。
不兼容或不回退到 `MAX_PROVIDER_KEY`，以避免凭据来源不明确。

### 3. 固定模型和端点

模型与端点属于代码内 provider 定义，`MODEL_NAME` 和 `MAX_GUI_BASE_URL` 均不覆盖它们。
这与当前 provider 契约一致，保证会话记录、测试与实际请求使用同一个模型标识。

## Risks / Trade-offs

- [七牛模型能力或配额可能随账户变化] → 单元测试只验证本地请求契约；真实 API Key 验证单列为
  外部端到端边界。
- [默认模型不支持某些图像或工具调用] → 保持通用 OpenAI 请求格式，失败时保留上游状态码和响应体，
  不伪造本地兼容分支。
- [密钥误提交] → 仅更新无值的 `.env.example`，不读取或写入真实 `.env`。

## Migration Plan

1. 实现注册表、配置说明与测试后，用户在本地 `.env` 填写 `MAX_QINIU_KEY` 并设置
   `MAX_PROVIDER=qiniu`。
2. 先运行配置与 MockTransport 合约测试，再由持有密钥的环境完成真实文本、图片和工具调用验证。
3. 如需回滚，移除 `qiniu` 注册项与文档、测试、规格增量；会话和持久化数据不需要迁移。

## Open Questions

无。
