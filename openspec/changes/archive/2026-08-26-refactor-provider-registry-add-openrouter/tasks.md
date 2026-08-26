## 1. Provider 定义与配置迁移

- [x] 1.1 新增带中文文档的不可变 provider 定义、注册表、解析与专属密钥校验
- [x] 1.2 让 Settings 从注册表解析模型、端点和密钥，并移除旧共享配置分支
- [x] 1.3 让客户端、消息编码与本地 serve 使用 provider 能力而不是名称集合

## 2. OpenRouter 与环境契约

- [x] 2.1 接入 OpenRouter 默认端点、`qwen/qwen3.5-plus`、Bearer 密钥和统一工具请求
- [x] 2.2 更新 `.env.example` 与 README，说明专属密钥和仅改 `MAX_PROVIDER` 的切换流程

## 3. 验证

- [x] 3.1 更新配置、客户端、CLI 测试，覆盖五个 provider、旧键失效和 OpenRouter 请求契约
- [x] 3.2 运行 Ruff format/check、相关 pytest 与 OpenSpec 严格验证并修复问题
