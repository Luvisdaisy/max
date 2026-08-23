## Why

多模态 GUI Agent 核心能力之一是“看懂屏幕、操作电脑”，这依赖大模型在图像理解和动作生成上的准确性。当前 Qwen3.5-4B 在本地部署时表现一般，第五周计划通过 LoRA 微调显著提升 GUI 任务成功率和动作格式准确率。

## What Changes

- 使用 Hugging Face Datasets + PEFT 实现对 Qwen3.5-4B 的 LoRA 微调。
- 构建基于 ScreenAgent 预处理数据集的监督训练集与验证集。
- 优化提示词工程，使模型更可靠地调用桌面工具。
- 产出微调后模型权重，并与现有 max-gui 架构兼容。

**BREAKING**: 现有模型版本号保持不变（不破坏现有推理后端）。

## Capabilities

### New Capabilities

- lora-finetune: 使用 PEFT 实现多模态大模型 LoRA 微调，提升 GUI 任务理解与动作生成能力

### Modified Capabilities

- multimodal-inference: 微调后模型可无缝切换到现有 vLLM 服务

## Impact

- 代码：src/max_gui/inference/、scripts/train_lora.py
- 数据：artifacts/datasets/screenagent/processed/
- 文档：docs/lora-finetune-plan.md（已存在）
- 依赖：PEFT、Accelerate、bitsandbytes
