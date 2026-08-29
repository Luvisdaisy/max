## Why

主推理层同时维护本机 `local` 和局域网 `remote`，但项目已接入固定的 WSL
Ollama 与云端 OpenAI 兼容服务。移除这两条历史路径可减少主模型权重、端口与
本机 `serve` 的维护面，并让未配置 `MAX_PROVIDER` 的运行统一进入 Ollama。

## What Changes

- **BREAKING**：从主推理 provider 注册表删除 `local` 与 `remote`；`MAX_PROVIDER`
  未设置时默认选择 `ollama`，显式设置 `local` 或 `remote` 时按未知 provider
  拒绝启动。
- **BREAKING**：移除 `max-gui serve` 及其本机主模型 vLLM 启动、权重校验和主模型
  专用配置。OCR 与 OmniParser 仍可使用独立 vLLM 环境，不受该 CLI 移除影响。
- 清理 local / remote 的配置样例、README 文案、测试与历史行为断言，并同步更新
  运行时和多模态推理规范。
- 从项目依赖中移除未被代码直接导入的 `modelscope` 包并更新锁文件；保留 OCR、
  OmniParser、LoRA 数据处理和训练仍使用的 PyTorch / Transformers 等依赖。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `runtime-config`：主 provider 名单、默认 provider 与可用配置项改为 Ollama 和
  保留的云端 provider。
- `multimodal-inference`：删除本机主模型权重检查、remote 请求和 `max-gui serve`
  契约，保留所有已注册 provider 的兼容请求与工具调用。

## Impact

- 受影响代码：`src/max_gui/provider.py`、`config.py`、`lifecycle.py`、`cli.py`、
  推理测试与 CLI 测试。
- 受影响文档与配置：`.env.example`、`README.md`、OpenSpec 基线规范。
- 受影响依赖：`pyproject.toml` 和 `uv.lock` 中的 `modelscope`；不移除 OCR、
  OmniParser 或 LoRA 脚本所需的模型相关依赖。
- 迁移：使用者应删除 `.env` 中的 `MAX_PROVIDER=local` 或 `remote`，或改为
  `MAX_PROVIDER=ollama`；现有 `max-gui serve` 调用不再受支持。
