# LORA微调计划

**日期**：2026-08-23  
**版本**：v1.0  
**大纲对应**：第5周「多模态大模型LORA微调与能力提升」  
**前提**：第3周已完成 ScreenAgent 数据集预处理（`artifacts/datasets/screenagent/processed/train.jsonl`、`test.jsonl`、`preview.jsonl` 存在，动作已映射为可执行工具）。

本计划基于现有仓库架构（Qwen3.5-4B + PEFT + Accelerate + vLLM + Hugging Face Datasets），提供完整、可落地的微调策略与实现步骤。

## 1. 微调目标

**核心目标**：让 Qwen3.5-4B（或 2B/9B 版本）在 GUI 任务理解与动作生成上显著提升，具体体现在：

- 屏幕截图 → 任务指令 → 子任务拆解 → 工具调用（`mouse_click`、`mouse_drag`、`keyboard_type`、`mouse_scroll`、`keyboard_press`）的准确率提升。
- 动作格式与坐标（视图像素）对齐当前 `max-gui` 工具协议。
- 提示词工程优化：让模型更可靠地使用 `screenshot` + `ocr` + `ocr_locate` 等工具。

**非目标**：不重训基础多模态能力，只做 LoRA 适配。

## 2. 数据集构建

### 2.1 当前数据集状态（已完成）
- `artifacts/datasets/screenagent/processed/` 已包含：
  - `train.jsonl`、`test.jsonl`（约 2000+ 样本，包含 `plan`、`act`、`reflect` 阶段）。
  - `preview.jsonl`（供人工核对）。
  - `stats.json`、`stats.md`（映射后工具频次、丢弃原因）。

### 2.2 构建训练集与验证集

**推荐比例**：train:val = 8:2（或 7:3，根据样本量调整）。

**转换脚本**（可复用 `scripts/prepare_screenagent.py` 扩展，或新增 `scripts/prepare_lora_dataset.py`）：

```python
# 示例：从 JSONL 构建带 prompt 的监督样本
{
  "source": "screenagent",
  "split": "train",
  "session_id": "...",
  "stage": "act",
  "instruction": "上网查找冯诺依曼的相关资料",
  "subtask": "浏览搜索结果，点击感兴趣的链接继续深入了解",
  "image": "artifacts/datasets/screenagent/train/.../2023-12-20_19-35-47-115314.jpg",
  "image_size": [1024, 768],
  "target": "根据现有屏幕图像的状态，按照以下格式输出动作：\n{tool_call_json_schema}\n",
  "actions": [
    {"tool": "mouse_click", "args": {"x": 368, "y": 319, "button": "left", "clicks": 1}}
  ]
}
```

**prompt 模板建议**（可放 `src/max_gui/agent/prompts.py` 或单独 `prompts/lora.py`）：

```python
SYSTEM_PROMPT = """你是 max-gui 的多模态 ReAct GUI Agent。
你只能使用工具调用格式输出动作：
{"tool": "mouse_click", "args": {...}}
{"tool": "mouse_drag", ...}
{"tool": "mouse_scroll", ...}
{"tool": "keyboard_type", "args": {"text": "..."}}
{"tool": "keyboard_press", "args": {"keys": ["enter"]}}

必须先调用 screenshot 工具获取最新屏幕图像，然后根据图像和子任务决策动作。
动作必须落在当前视图像素范围内。坐标用视图像素（1024×768 基准），后续工具会自动换算到逻辑像素。"""

USER_TEMPLATE = """屏幕图像：{image_url}

任务：{instruction}

当前子任务：{subtask}

请输出下一步动作。"""
```

### 2.3 数据增强建议
- 随机翻转/缩放图像（多模态模型对位置不敏感）。
- 增加少量负例（不执行的动作）。
- 平衡阶段分布（plan / act / reflect）。

## 3. 模型选择与 LoRA 配置

**基础模型**：`Qwen/Qwen3.5-4B`（推荐）或 `Qwen/Qwen3.5-2B`（资源受限时）。

**LoRA 配置**（推荐参数）：

```json
{
  "lora_rank": 64,           # 平衡质量与速度
  "lora_alpha": 32,
  "lora_dropout": 0.05,
  "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],  # Qwen 典型
  "modules_to_save": ["embed_tokens", "lm_head"]  # 保留嵌入层
}
```

**训练超参数**：

| 参数               | 推荐值                  | 说明                     |
|--------------------|-------------------------|--------------------------|
| batch_size         | 4（per_device 2 + gradient_accumulation 2） | 显存友好                |
| learning_rate      | 1e-4                   | Qwen 微调常用            |
| epochs             | 3–5                    | 避免过拟合              |
| max_length         | 2048                   | 图片+文本总长度         |
| warmup_ratio       | 0.1                    | -                       |
| weight_decay       | 0.01                   | -                       |

## 4. 训练与部署架构

### 4.1 依赖
- `uv add peft transformers accelerate bitsandbytes datasets`
- `max-gui serve` 启动的 vLLM 作为推理后端（OpenAI 兼容）。

### 4.2 训练命令示例

```bash
# 启动 vLLM（已有）
max-gui serve

# 训练脚本（使用 Hugging Face Trainer）
python scripts/train_lora.py \
  --model_name Qwen/Qwen3.5-4B \
  --dataset artifacts/datasets/screenagent/processed/train.jsonl \
  --val_dataset artifacts/datasets/screenagent/processed/test.jsonl \
  --output_dir model/qwen3.5-4b-lora \
  --batch_size 4 \
  --learning_rate 1e-4 \
  --num_train_epochs 4 \
  --save_steps 100
```

### 4.3 微调后部署

1. 使用 `PEFT` 合并 LoRA 权重。
2. 导出为 `model/qwen3.5-4b-lora`（与现有 `qwen3.5-4b` 结构兼容）。
3. 更新 `.env` 或 `config.py` 中的 `MODEL_NAME` 为 `qwen3.5-4b-lora`。
4. 重启 `max-gui serve`。

## 5. 效果评估与对比

**微调前后对比指标**：

- GUI 任务成功率（在 5–10 个基础桌面任务上）。
- 动作格式准确率（JSON schema 合规率）。
- 坐标定位准确率（与实际屏幕对齐）。
- token 使用量 / 推理速度。

**评估脚本**：

```python
# 示例：用当前 max-gui 跑 10 个任务，统计成功率
python scripts/eval_lora.py --model qwen3.5-4b-lora
```

**输出**：微调效果对比分析报告（Markdown + 图表）。

## 6. 风险与注意事项

- **显存**：4B LoRA 仍需 ~8–12GB GPU；2B 版本更友好。
- **数据集质量**：ScreenAgent 样本已人工修正，负例已过滤。
- **提示词工程**：必须让模型理解“先截图、再决策工具”。
- **合并后测试**：必须在真实 macOS 上验证坐标换算与工具调用。
- **资源**：本地 GPU 或 Google Colab。

## 7. 交付物

- `model/qwen3.5-4b-lora/`（权重 + config）。
- `docs/lora-finetune-plan.md`（本文件）。
- `artifacts/datasets/screenagent/processed/`（扩展后 JSONL）。
- 微调效果对比分析报告。

---

**建议下一步**：执行第3周预处理脚本后，即可运行本计划的训练脚本。需要我生成 `scripts/train_lora.py` 模板或更新 `docs/gui-datasets-week3.md` 吗？