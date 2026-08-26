## Context

当前 max-gui 使用 Qwen3.5-4B 作为默认本地多模态推理模型，桌面工具协议已稳定（screenshot、mouse_*/keyboard_*、ocr_locate）。第3周已完成 ScreenAgent 数据集预处理，第4周已集成端到端 ReAct 闭环。第五周计划通过 LoRA 微调显著提升 GUI 任务成功率。

## Goals / Non-Goals

**Goals:**
- 使用 PEFT 实现 LoRA 微调，提升模型在屏幕理解、子任务规划和工具调用上的准确率。
- 产出兼容现有 vLLM 服务的微调模型权重。
- 构建可对比微调前后的评估脚本。

**Non-Goals:**
- 不重训基础模型，只做参数高效微调。
- 不新增新模型架构。
- 不改变现有工具调用协议。

## Decisions

- 训练集与验证集使用预处理后的 JSONL，带 prompt 模板。
- LoRA rank 64，alpha 32，target_modules 覆盖 Qwen 典型注意力和 FFN 层。
- 使用 Accelerate + bitsandbytes 进行 4/8 位量化加速。
- 提示词模板已优化为“先截图 + 决策工具调用”格式。
- macOS 使用 `remote` 后端访问家庭局域网内 WSL 的受限网关；远端端点配置
  `MAX_GUI_BASE_URL`，客户端不检查 macOS 本地权重，也不要求 API Key。网关仅开放
  `/health`、`/v1/models` 与 `/v1/chat/completions`，Windows 防火墙限制为可信局域网来源。

## Risks / Trade-offs

- 显存占用：4B LoRA 仍需较高显存，建议使用 2B 版本。
- 过拟合风险：数据集样本量有限，可增加数据增强。
- 合并后兼容性：必须在真实 macOS 上验证坐标换算和工具调用。

## Migration Plan

- WSL 合并权重后由项目网关公开 `8000`，vLLM 后端仅监听 `127.0.0.1:8001`；Windows
  防火墙仅允许 macOS 的保留 LAN IP 或可信局域网。
- macOS 设置 `MAX_PROVIDER=remote`、`MODEL_NAME=qwen3.5-4b-lora` 与远程
  `MAX_GUI_BASE_URL=http://192.168.1.158:8000/v1`；不设置 `MAX_PROVIDER_KEY`，也不运行
  `max-gui serve`。
- 保持原有 local、modelscope、dashscope 后端兼容。

## Open Questions

- 最终 LoRA rank 是否调整为 128？
- 是否需要增加负例对比学习？
