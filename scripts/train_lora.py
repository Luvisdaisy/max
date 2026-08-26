"""训练或合并 max-gui 的 Qwen3.5 LoRA 权重。

训练数据必须是 ``prepare_screenagent.py`` 生成的 JSONL。脚本把其中的
``actions`` 规范成当前桌面工具协议，再以图像、任务和子任务为输入做监督
微调；训练产物先保存为 PEFT adapter，随后可用 ``--merge-adapter`` 导出为
vLLM 可直接加载的完整权重目录。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = PROJECT_ROOT / "model" / "qwen3.5-4b"
DEFAULT_TRAIN = (
    PROJECT_ROOT / "artifacts" / "datasets" / "screenagent" / "processed" / "train.jsonl"
)
DEFAULT_TEST = PROJECT_ROOT / "artifacts" / "datasets" / "screenagent" / "processed" / "test.jsonl"
DEFAULT_ADAPTER = PROJECT_ROOT / "artifacts" / "models" / "qwen3.5-4b-lora-adapter"
DEFAULT_MERGED = PROJECT_ROOT / "model" / "qwen3.5-4b-lora"
DEFAULT_MAX_PIXELS = 1024 * 768
LORA_TARGET_MODULES = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")

SYSTEM_PROMPT = """你是 max-gui 的多模态 ReAct GUI Agent。
根据当前屏幕、任务和子任务，输出下一步的 JSON，不要输出解释或 Markdown。
动作只能使用 mouse_click、mouse_move、mouse_drag、mouse_scroll、keyboard_type、
keyboard_press；keyboard_press 的 keys 必须是非空字符串数组。坐标以当前截图像素为准。"""


@dataclass(frozen=True, slots=True)
class LoraArguments:
    """LoRA 与训练的可复现默认参数。"""

    rank: int = 64
    alpha: int = 32
    dropout: float = 0.05
    batch_size: int = 1
    gradient_accumulation_steps: int = 4
    learning_rate: float = 1e-4
    epochs: float = 4.0
    max_length: int = 2048
    max_pixels: int = DEFAULT_MAX_PIXELS


def load_records(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 并拒绝空行、非法 JSON 或非对象记录。

    参数：path 为预处理后的 JSONL 文件。
    返回：按文件顺序排列的记录。
    异常：ValueError 表示数据不可用于训练。
    """
    if not path.is_file():
        raise ValueError(f"数据集不存在：{path}")
    records: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{number} 不是合法 JSON") from exc
        if not isinstance(item, dict):
            raise ValueError(f"{path}:{number} 必须是 JSON 对象")
        records.append(item)
    if not records:
        raise ValueError(f"数据集为空：{path}")
    return records


def canonical_target(record: dict[str, Any]) -> str:
    """将 ScreenAgent 记录收敛为可由当前工具协议消费的监督目标。"""
    stage = str(record.get("stage") or "act")
    if stage == "plan":
        payload: object = {"plan": list(record.get("plan") or [])}
    elif stage == "reflect":
        payload = {
            "situation": str(record.get("situation") or ""),
            "advice": str(record.get("advice") or ""),
        }
    else:
        payload = list(record.get("actions") or [])
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def messages_for(record: dict[str, Any], image_path: Path) -> list[dict[str, Any]]:
    """生成含本地截图引用的 Qwen Chat Template 消息。"""
    instruction = str(record.get("instruction") or "")
    subtask = str(record.get("subtask") or "")
    user_text = f"任务：{instruction}\n当前子任务：{subtask}\n请输出下一步。"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": str(image_path)},
                {"type": "text", "text": user_text},
            ],
        },
        {"role": "assistant", "content": canonical_target(record)},
    ]


def validate_records(records: Iterable[dict[str, Any]], root: Path) -> None:
    """检查记录的必需字段与图片路径，避免训练到一半才因数据错误退出。"""
    for number, record in enumerate(records, start=1):
        image = record.get("image")
        if not isinstance(image, str) or not image:
            raise ValueError(f"第 {number} 条缺少 image")
        if not (root / image).is_file():
            raise ValueError(f"第 {number} 条图片不存在：{root / image}")
        if str(record.get("stage") or "act") == "act" and not isinstance(
            record.get("actions"), list
        ):
            raise ValueError(f"第 {number} 条 act 记录缺少 actions 数组")


def _imports() -> tuple[Any, ...]:
    """延迟导入可选训练依赖，普通脚本检查无需安装 GPU 训练栈。"""
    try:
        import torch
        from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForImageTextToText,
            AutoProcessor,
            Trainer,
            TrainingArguments,
        )
    except ImportError as exc:
        raise RuntimeError(
            "缺少训练依赖。请执行 `uv sync`，或安装 peft、transformers、accelerate 与 torch。"
        ) from exc
    return (
        torch,
        LoraConfig,
        PeftModel,
        get_peft_model,
        prepare_model_for_kbit_training,
        AutoModelForImageTextToText,
        AutoProcessor,
        Trainer,
        TrainingArguments,
    )


def train(args: argparse.Namespace) -> None:
    """加载视觉语言模型，执行 LoRA 监督训练并保存 adapter。"""
    train_records = load_records(args.dataset)
    validation_records = load_records(args.val_dataset)
    validate_records([*train_records, *validation_records], PROJECT_ROOT)
    if args.dry_run:
        print(f"数据检查通过：train={len(train_records)}，validation={len(validation_records)}")
        return

    (
        torch,
        LoraConfig,
        _,
        get_peft_model,
        prepare_model_for_kbit_training,
        AutoModelForImageTextToText,
        AutoProcessor,
        Trainer,
        TrainingArguments,
    ) = _imports()
    try:
        processor = AutoProcessor.from_pretrained(
            args.model, trust_remote_code=args.trust_remote_code
        )
    except ImportError as exc:
        raise RuntimeError(
            "Qwen3.5 多模态处理器需要 torchvision；请执行 `uv sync` 后重试。"
        ) from exc
    model_kwargs: dict[str, Any] = {
        "torch_dtype": "auto",
        "trust_remote_code": args.trust_remote_code,
    }
    if args.load_in_4bit:
        from transformers import BitsAndBytesConfig

        model_kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
        model_kwargs["device_map"] = "auto"
    model = AutoModelForImageTextToText.from_pretrained(args.model, **model_kwargs)
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    if args.load_in_4bit:
        model = prepare_model_for_kbit_training(model)
    model = get_peft_model(
        model,
        LoraConfig(
            r=args.rank,
            lora_alpha=args.alpha,
            lora_dropout=args.dropout,
            target_modules=list(LORA_TARGET_MODULES),
            task_type="CAUSAL_LM",
        ),
    )

    class ScreenAgentDataset(torch.utils.data.Dataset):
        """将一条 ScreenAgent JSONL 记录编码为多模态监督样本。"""

        def __init__(self, records: list[dict[str, Any]]) -> None:
            """参数：records 为已验证的 JSONL 记录。"""
            self.records = records

        def __len__(self) -> int:
            """返回样本数。"""
            return len(self.records)

        def __getitem__(self, index: int) -> dict[str, Any]:
            """读取截图并掩蔽 assistant 回复之前的 token。"""
            record = self.records[index]
            image_path = PROJECT_ROOT / str(record["image"])
            all_messages = messages_for(record, image_path)
            prompt_messages = all_messages[:-1]
            full_text = processor.apply_chat_template(
                all_messages, tokenize=False, add_generation_prompt=False
            )
            prompt_text = processor.apply_chat_template(
                prompt_messages, tokenize=False, add_generation_prompt=True
            )
            encoded = processor(
                text=[full_text],
                images=[str(image_path)],
                max_length=args.max_length,
                max_pixels=args.max_pixels,
                padding=False,
                truncation=True,
                return_tensors="pt",
            )
            prefix = processor(
                text=[prompt_text],
                images=[str(image_path)],
                max_length=args.max_length,
                max_pixels=args.max_pixels,
                padding=False,
                truncation=True,
                return_tensors="pt",
            )["input_ids"].shape[1]
            item = {name: value.squeeze(0) for name, value in encoded.items()}
            labels = item["input_ids"].clone()
            labels[:prefix] = -100
            item["labels"] = labels
            return item

    def collate(features: list[dict[str, Any]]) -> dict[str, Any]:
        """按 batch 补齐文本；图像 patch 维度由 Qwen processor 原样保留。"""
        if len(features) != 1:
            raise ValueError(
                "当前多模态 collator 仅支持每设备 batch_size=1；请用梯度累积扩大有效批次"
            )
        return {name: value.unsqueeze(0) for name, value in features[0].items()}

    training_args = TrainingArguments(
        output_dir=str(args.adapter_output_dir),
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        num_train_epochs=args.epochs,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch",
        remove_unused_columns=False,
        report_to=[],
        dataloader_pin_memory=False,
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=ScreenAgentDataset(train_records),
        eval_dataset=ScreenAgentDataset(validation_records),
        data_collator=collate,
    )
    trainer.train()
    args.adapter_output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.adapter_output_dir)
    processor.save_pretrained(args.adapter_output_dir)
    print(f"LoRA adapter 已保存到：{args.adapter_output_dir}")


def merge_adapter(adapter: Path, model: Path, output: Path, trust_remote_code: bool) -> None:
    """把 adapter 合并到基础模型，输出供 vLLM 直接加载的完整权重。"""
    _, _, PeftModel, _, _, AutoModelForImageTextToText, AutoProcessor, _, _ = _imports()
    base = AutoModelForImageTextToText.from_pretrained(
        model, torch_dtype="auto", trust_remote_code=trust_remote_code
    )
    merged = PeftModel.from_pretrained(base, adapter).merge_and_unload()
    output.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(output, safe_serialization=True)
    AutoProcessor.from_pretrained(model, trust_remote_code=trust_remote_code).save_pretrained(
        output
    )
    print(f"已合并完整权重到：{output}")


def parser() -> argparse.ArgumentParser:
    """构建训练与合并共用的命令行参数。"""
    defaults = LoraArguments()
    command = argparse.ArgumentParser(description="训练或合并 Qwen3.5 的 max-gui LoRA 权重")
    command.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    command.add_argument("--dataset", type=Path, default=DEFAULT_TRAIN)
    command.add_argument("--val-dataset", type=Path, default=DEFAULT_TEST)
    command.add_argument("--adapter-output-dir", type=Path, default=DEFAULT_ADAPTER)
    command.add_argument("--rank", type=int, default=defaults.rank)
    command.add_argument("--alpha", type=int, default=defaults.alpha)
    command.add_argument("--dropout", type=float, default=defaults.dropout)
    command.add_argument("--batch-size", type=int, default=defaults.batch_size)
    command.add_argument(
        "--gradient-accumulation-steps", type=int, default=defaults.gradient_accumulation_steps
    )
    command.add_argument("--learning-rate", type=float, default=defaults.learning_rate)
    command.add_argument("--epochs", type=float, default=defaults.epochs)
    command.add_argument("--max-length", type=int, default=defaults.max_length)
    command.add_argument("--max-pixels", type=int, default=defaults.max_pixels)
    command.add_argument("--load-in-4bit", action="store_true")
    command.add_argument("--trust-remote-code", action="store_true")
    command.add_argument("--dry-run", action="store_true")
    command.add_argument("--merge-adapter", type=Path)
    command.add_argument("--merged-output-dir", type=Path, default=DEFAULT_MERGED)
    return command


def main(argv: Sequence[str] | None = None) -> int:
    """解析命令行；训练前做参数和数据检查，合并模式不读取数据集。"""
    args = parser().parse_args(argv)
    if args.merge_adapter:
        merge_adapter(
            args.merge_adapter, args.model, args.merged_output_dir, args.trust_remote_code
        )
        return 0
    if args.batch_size != 1:
        raise ValueError("多模态动态图像 patch 仅支持 --batch-size 1；请调大梯度累积")
    if args.rank <= 0 or args.alpha <= 0 or not 0 <= args.dropout < 1:
        raise ValueError("rank、alpha 必须大于 0，dropout 必须在 [0, 1) 内")
    train(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        print(f"训练未启动：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
