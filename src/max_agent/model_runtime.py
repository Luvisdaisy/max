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
    """Load Qwen3.5-4B with the native offline Transformers implementation."""
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
    """Validate the supported Qwen3.5-4B files required for offline loading."""
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
    """Verify an explicitly supplied image can be decoded without preserving it."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(image) as source:
            source.verify()
    except (FileNotFoundError, OSError, UnidentifiedImageError):
        raise ValueError(
            "offline benchmark requires a readable local image supplied with --image"
        ) from None
    return image.resolve()
