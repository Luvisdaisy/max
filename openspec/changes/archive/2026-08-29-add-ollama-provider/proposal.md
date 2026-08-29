## Why

用户已经在局域网 WSL 上运行 Ollama 的 OpenAI 兼容服务，但当前 provider 注册表无法选择该服务，导致 max-gui 不能以固定、可复现的配置连接 `qwen3.5:9b`。

## What Changes

- 新增无密钥的 `ollama` provider，固定使用 WSL 服务的 OpenAI 兼容根端点与 `qwen3.5:9b` 模型。
- 将 Ollama 纳入 provider 注册表、配置示例、用户文档与拒绝本机 `serve` 的既有流程。
- 为配置解析与 OpenAI 兼容请求补充覆盖 Ollama 的自动化测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-config`：允许选择并说明无密钥的局域网 Ollama provider。
- `multimodal-inference`：让 Ollama 复用现有 OpenAI 兼容请求、工具调用和网络错误提示链路。

## Impact

- 受影响代码：`src/max_gui/provider.py`、配置加载、CLI 生命周期的既有 provider 注册表路径。
- 受影响文档：`.env.example` 与 `README.md`。
- 受影响测试：`tests/test_inference.py`、`tests/test_cli.py`；不引入依赖，也不修改远端服务。
