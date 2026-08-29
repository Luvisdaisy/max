## Context

主推理 provider 注册表目前保留 `local`、`remote`、`ollama` 与三个云端
provider。`local` 同时驱动 `max-gui serve`、主模型权重检查和一组配置字段；
`remote` 是固定局域网 vLLM 端点。OCR 与 OmniParser 虽也通过独立 vLLM 进程运行，
但它们复用的是二进制定位，不依赖主推理 provider 或 `serve` 子命令。

工作区已有未提交的 `add-ollama-provider` change。该 change 的 Ollama 定义和测试
必须保留，并作为移除本地、远端后默认入口。

## Goals / Non-Goals

**Goals:**

- 仅保留 Ollama、ModelScope、DashScope、OpenRouter 作为主推理 provider。
- 将无 `MAX_PROVIDER` 的配置稳定解析为固定的 Ollama 定义。
- 删除主模型本地启动与权重校验，且不影响 OCR、OmniParser、LoRA 脚本。
- 移除无直接代码导入的 `modelscope` 安装包。

**Non-Goals:**

- 不修改 WSL Ollama 服务、局域网地址、防火墙或其模型能力。
- 不移除 OCR / OmniParser 的独立 vLLM 启动、PyTorch / Transformers，或 LoRA
  数据处理和训练脚本。
- 不改动其余 provider 的模型、端点、鉴权或工具调用协议。

## Decisions

- 默认 provider 设为 `ollama`。这是唯一保留的无密钥 provider，并与现有
  `add-ollama-provider` change 一致；替代方案是选一个云端 provider，但那会让没有
  密钥的初始配置立即失败。
- 删除 `max-gui serve`、`serve_model` 和主模型 `_serve_command`，同时保留
  `resolve_vllm_bin` 与 `MissingVllmError`。后者仍被 OCR、OmniParser 与演示脚本
  调用；把它们一并移除会破坏不属于主 provider 的能力。
- 删除主模型 `require_weights`、`MissingWeightsError`、`model_path` 与仅被主模型
  `serve` 使用的 `MAX_GUI_GPU_MEM`。保留 `MAX_GUI_MAX_MODEL_LEN` 与
  `MAX_GUI_DTYPE`，因为 OCR vLLM 命令仍使用它们。
- 仅移除 `modelscope` 依赖。静态搜索表明它没有 Python import；`modelscope`
  provider 通过 OpenAI 兼容 HTTP 调用。训练和视觉运行时依赖仍有实际引用，不能按
  名称推断为 local 的附属依赖。

## Risks / Trade-offs

- [默认 Ollama 局域网服务不可达] → 保留既有连接失败提示；用户可显式切换到已配置
  的云端 provider。
- [已有 `.env` 继续指定 local 或 remote] → 作为未知 provider 及早中文报错；README
  和示例给出迁移目标。
- [误删 OCR 所需 vLLM 支撑] → 测试仍覆盖 OCR / OmniParser 的二进制解析和 OCR 命令，
  且实现时不删除该共用能力。
- [与未提交 Ollama change 冲突] → 在同一工作树上最小化修改；实现前先核验并保留
  `ollama` 注册项和已有测试。

## Migration Plan

1. 将 `.env` 中的 `MAX_PROVIDER=local` 或 `remote` 改为 `ollama`，或选择已配置的
   云端 provider。
2. 删除调用 `max-gui serve` 的脚本或文档步骤，直接启动外部 Ollama 服务。
3. 若 Ollama 不可用，设置任一保留云端 provider 和其专属密钥；不存在 local / remote
   回滚路径。

## Open Questions

无。
