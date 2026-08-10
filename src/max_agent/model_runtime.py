"""离线 Qwen 模型与输入图像的加载前置校验。"""

from __future__ import annotations

import json
from pathlib import Path

QWEN35_MODEL_PATH = Path("model/Qwen/Qwen3.5-4B")
REQUIRED_MODEL_FILES = (
    "config.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "model.safetensors.index.json",
)


def load_qwen35_model(model_dir: Path) -> object:
    """使用原生 Transformers 离线加载 Qwen3.5-4B，并启用 BF16 CUDA 推理。"""
    import torch
    from transformers import AutoModelForMultimodalLM

    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    return (
        AutoModelForMultimodalLM.from_pretrained(
            str(model_dir), dtype=torch.bfloat16, local_files_only=True
        )
        .to("cuda")
        .eval()
    )


def require_complete_local_model(repository_root: Path, model_dir: Path) -> Path:
    """校验受支持模型及其全部权重文件，阻止不完整或仓库外加载。"""
    resolved = model_dir.resolve()
    expected = (repository_root / QWEN35_MODEL_PATH).resolve()
    if resolved != expected:
        raise ValueError(
            "offline benchmark requires the supported local Qwen3.5-4B model; run max-agent download-model"
        )
    missing = [name for name in REQUIRED_MODEL_FILES if not (resolved / name).is_file()]
    if missing:
        raise FileNotFoundError(
            "offline benchmark requires a complete local Qwen3.5-4B model; rerun max-agent download-model"
        )
    try:
        weight_index = json.loads(
            (resolved / "model.safetensors.index.json").read_text(encoding="utf-8")
        )
        weight_files = set(weight_index["weight_map"].values())
    except (json.JSONDecodeError, KeyError, TypeError):
        raise ValueError(
            "offline benchmark requires a valid local Qwen3.5-4B weight index; rerun max-agent download-model"
        ) from None
    if not weight_files or any(
        not (resolved / name).is_file() for name in weight_files
    ):
        raise FileNotFoundError(
            "offline benchmark requires complete local Qwen3.5-4B weights; rerun max-agent download-model"
        )
    return resolved


def require_readable_image(image: Path) -> Path:
    """验证显式传入的本地图像可解码，但不保留或复制输入内容。"""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(image) as source:
            source.verify()
    except (FileNotFoundError, OSError, UnidentifiedImageError):
        raise ValueError(
            "offline benchmark requires a readable local image supplied with --image"
        ) from None
    return image.resolve()
