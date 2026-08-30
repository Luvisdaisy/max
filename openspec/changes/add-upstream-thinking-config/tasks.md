## 1. 配置与 provider 映射

- [x] 1.1 在 Settings 中解析严格布尔的 `MAX_GUI_ENABLE_THINKING`，缺省关闭并提供中文非法值错误。
- [x] 1.2 在 provider 注册表集中定义五个后端的上游 thinking 请求字段映射。

## 2. 请求、文档与测试

- [x] 2.1 让 `InferenceClient` 合并 provider 生成的 thinking 负载，同时保留既有 reasoning 解析和回传。
- [x] 2.2 更新 `.env.example` 与 README 的既定配置章节，说明默认关闭和启用方式。
- [x] 2.3 增加配置与 MockTransport 测试，覆盖缺省、解析错误、五个 provider 的启用和关闭请求体，以及上游 4xx 不降级重试。

## 3. 验证

- [x] 3.1 已用 `.venv/bin/ruff` 格式化本次触及 Python 文件、检查 `src tests`，并运行 `tests/test_inference.py`（105 passed）与 OpenSpec 严格校验。
- [x] 3.2 未提供各 provider 的真实凭据，未执行 Ollama、ModelScope、DashScope、OpenRouter 与七牛的真实文本／图片／工具端到端开关验证；MockTransport 契约测试已覆盖请求负载。
