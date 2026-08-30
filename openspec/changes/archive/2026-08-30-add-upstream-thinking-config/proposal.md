## Why

当前客户端只能解析和展示上游返回的思考内容，无法控制模型是否生成思考；这会导致延迟和
Token 成本无法由部署者统一管理。需要一个默认关闭的环境变量，将同一意图映射到各 provider
的上游请求字段。

## What Changes

- 新增布尔环境变量 `MAX_GUI_ENABLE_THINKING`，缺省为 `false`，并拒绝非法值。
- 在 Settings 中保存已解析的开关，并让每次 `/chat/completions` 请求显式传递当前 provider
  对应的“启用／关闭上游思考”字段。
- 在 provider 定义中集中维护请求参数映射：Ollama 使用 `think`，ModelScope 与 DashScope
  使用 `enable_thinking`，OpenRouter 使用 `reasoning.enabled`，七牛使用
  `thinking.type`（`enabled`／`disabled`）。
- 更新 `.env.example`、README、运行时配置和 MockTransport 测试；保留已有的思考流解析与
  DashScope 历史 `reasoning_content` 回传行为。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-config`：加入统一的、默认关闭的上游 thinking 配置。
- `multimodal-inference`：要求按 provider 将开关映射到每个 Chat Completions 请求。

## Impact

- 影响 `src/max_gui/provider.py`、`src/max_gui/config.py`、`src/max_gui/inference/client.py`、
  `.env.example`、README 与推理测试。
- 不新增 SDK 或依赖，不隐藏已经返回的 reasoning，不改变工具调用、会话格式或模型选择。
- 启用开关可能增加上游延迟和输出 Token；仅思考模型或上游能力变更仍可能拒绝关闭请求。
