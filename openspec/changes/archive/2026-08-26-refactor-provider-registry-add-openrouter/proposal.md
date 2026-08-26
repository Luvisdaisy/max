## Why

推理后端的模型、端点、鉴权和能力判断目前分散在 `config.py`、`client.py` 与 CLI 中，新增后端需要重复修改名称分支，容易造成配置和运行行为不一致。需要建立单一 provider 定义源，并在保持统一 OpenAI 兼容 Chat Completions 契约的前提下加入 OpenRouter。

## What Changes

- 新增独立 `provider.py`，集中定义 provider 名称、默认模型、OpenAI 兼容根端点、密钥环境变量名和运行能力。
- `local`、`remote`、`modelscope`、`dashscope` 与新增 `openrouter` 全部共用现有 `/chat/completions`、SSE、工具调用和多模态消息链路。
- 新增 `openrouter`，固定根端点为 `https://openrouter.ai/api/v1`，默认模型为 `qwen/qwen3.5-plus`。
- 将云端密钥拆为 provider 专属环境变量，使 `.env` 可同时保存各后端密钥，切换时只需修改 `MAX_PROVIDER`。
- **BREAKING**：移除 provider 共享的 `MAX_PROVIDER_KEY` 与运行时 `MODEL_NAME` 覆盖；provider 模型与非敏感端点改由 Python 定义维护。
- 保留 Agent、图像、OCR、OmniParser 和本地 vLLM 运行参数的既有环境变量行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-config`：调整 provider 选择、专属密钥与代码内 provider 定义的配置契约。
- `multimodal-inference`：加入 OpenRouter，并规定全部 provider 共享 OpenAI 兼容 Chat Completions 行为。

## Impact

- 主要影响 `src/max_gui/provider.py`、`src/max_gui/config.py`、`src/max_gui/inference/client.py`、`src/max_gui/cli.py` 与 `src/max_gui/lifecycle.py`。
- 更新 `.env.example`、`README.md`、配置/客户端/CLI 测试及对应 OpenSpec 规格。
- 不新增 OpenAI SDK 或 OpenRouter SDK，继续使用现有 `httpx` 客户端；不加入 OpenAI Auth，不改变会话数据格式。
