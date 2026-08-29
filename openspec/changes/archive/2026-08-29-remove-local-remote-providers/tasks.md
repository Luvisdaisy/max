## 1. 主推理 provider 与配置

- [x] 1.1 从 provider 注册表删除 `local`、`remote` 及主模型本地能力字段，将默认 provider 改为 `ollama`。
- [x] 1.2 移除主模型权重校验与 `max-gui serve` 流程，同时保留 OCR、OmniParser 和演示脚本所需的 vLLM 二进制定位能力。
- [x] 1.3 清理已废弃的主模型显存配置，并更新配置加载、错误文案和中文代码文档。

## 2. 依赖、文档与测试

- [x] 2.1 从项目依赖和锁文件移除无直接导入的 `modelscope` 包，不修改 OCR、OmniParser 或 LoRA 仍使用的依赖。
- [x] 2.2 更新 `.env.example` 与 README：默认 Ollama，删除 local / remote / `serve` 说明并写明迁移方式。
- [x] 2.3 删除 local、remote 与主模型 `serve` 测试；补充默认 Ollama、已移除 provider 拒绝和 OCR / OmniParser vLLM 路径未回归的覆盖。

## 3. 验证

- [x] 3.1 运行 `uv run ruff format src tests` 与 `uv run ruff check src tests`。
- [x] 3.2 运行相关 pytest 与完整测试集，并执行 OpenSpec 严格校验；将实际结果与未验证的局域网 Ollama 端到端状态分开记录。
