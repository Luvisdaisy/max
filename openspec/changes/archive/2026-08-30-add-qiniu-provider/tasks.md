## 1. Provider 与配置

- [x] 1.1 在不可变 provider 注册表新增 `qiniu`，固定模型、根端点、专属密钥变量、保守上下文预算与中文连接提示。
- [x] 1.2 更新运行配置的环境变量说明和 `.env.example`，仅通过 `MAX_QINIU_KEY` 读取七牛密钥。

## 2. 文档与测试

- [x] 2.1 更新 README 的既定配置章节，说明 `MAX_PROVIDER=qiniu` 的启用方式与密钥要求。
- [x] 2.2 补充配置和客户端 MockTransport 测试，覆盖固定模型与端点、Bearer 认证、缺密钥不发请求、工具 schema 与网络失败提示。

## 3. 验证

- [x] 3.1 已因 `uv` 缓存权限受限改用 `.venv/bin/ruff`：格式化本次触及文件，并对 `src tests` 完成 `ruff check`。
- [x] 3.2 已运行 `tests/test_inference.py`（88 passed）与 OpenSpec 严格校验；未提供七牛 API Key，真实账号、视觉输入与工具调用端到端验证尚未执行。
