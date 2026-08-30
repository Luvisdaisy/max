## Why

现有主推理 provider 没有七牛 AI Token API，用户无法通过现有统一的 OpenAI Chat
Completions 链路使用七牛提供的模型。七牛接口兼容该协议，适合以最小改动接入并复用现有
多模态、流式响应与工具调用能力。

## What Changes

- 在 Python provider 注册表新增名称为 `qiniu` 的云端 provider。
- 固定使用七牛 OpenAI 兼容根端点 `https://api.qnaigc.com/v1` 与默认模型
  `z-ai/glm-5.3-flash`。
- 新增专属环境变量 `MAX_QINIU_KEY`，缺失时在发起 HTTP 请求前给出中文提示。
- 将 `qiniu` 纳入现有 provider 配置、网络失败提示、`.env.example`、README 和测试契约。
- 复用既有 `/chat/completions`、SSE、图像消息与 `tools` / `tool_choice=auto` 请求链路；
  不引入七牛专属 SDK。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-config`：将 `qiniu` 和其专属密钥、固定模型及根端点加入主推理 provider 配置契约。
- `multimodal-inference`：将七牛纳入统一 OpenAI 兼容推理、认证、网络错误与工具调用契约。

## Impact

- 修改 `src/max_gui/provider.py`、`src/max_gui/config.py`、推理相关测试，以及
  `.env.example` 和 README 的 provider 说明。
- 不新增运行依赖，不改变 CLI、会话格式、Agent 工具协议、OCR 或 OmniParser。
- 实际账户、模型的视觉输入和工具调用可用性须用用户的七牛 API Key 做独立端到端验证。
