## 1. 配置

- [x] 1.1 `PROVIDERS` 增加 `bailian`；`Settings` 增加业务空间字段；`load_settings` 在 `bailian` 下默认 `MODEL_NAME=qwen3.8-27b`，`base_url` 为 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`，密钥仍读 `MAX_PROVIDER_KEY`
- [x] 1.2 `bailian` 缺 `MAX_PROVIDER_KEY` 或 `MAX_BAILIAN_WORKSPACE` 时中文报错，不提示 `max-gui serve`；不认 `DASHSCOPE_API_KEY`；非法 provider 文案列出 `bailian`
- [x] 1.3 `.env.example` 注释 `bailian`、`MAX_BAILIAN_WORKSPACE` 与默认 `qwen3.8-27b`
- [x] 1.4 测试：bailian 默认模型名与端点、缺 key、缺 Workspace、`DASHSCOPE_API_KEY` 不算密钥、local 不要求 Workspace

## 2. 客户端与 serve

- [x] 2.1 `bailian` 跳过本地权重；发请求前校验 key 与 Workspace；连接失败文案不含 `max-gui serve`
- [x] 2.2 `to_chat_messages`：仅 `bailian` 且助手有 `reasoning` 时设置 `reasoning_content`，不拼进 `content`；`local` / `modelscope` 不变
- [x] 2.3 `think` / 客户端在 `bailian` 下仍发送 `tools` 与 `tool_choice=auto`；`max-gui serve` 在 `bailian` 下非零退出
- [x] 2.4 测试：bailian 请求 URL 含 Workspace 与 `compatible-mode/v1`、无本地目录仍发请求、mock SSE tools、思考回传、无思考不加字段、serve 拒绝

## 3. 收尾

- [x] 3.1 `uv run ruff format src tests` 与 `uv run ruff check src tests`；相关测试通过
