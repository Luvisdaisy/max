from __future__ import annotations

from pathlib import Path

from .config import assert_project_model_dir


def load_qwen35_model(model_dir: Path) -> object:
    """Load Qwen3.5-4B with the native offline Transformers implementation."""
    import torch
    from transformers import AutoModelForMultimodalLM

    torch.cuda.reset_peak_memory_stats()
    return AutoModelForMultimodalLM.from_pretrained(
        str(model_dir), dtype=torch.bfloat16, local_files_only=True
    ).to("cuda").eval()


def require_complete_local_model(repository_root: Path, model_dir: Path) -> Path:
    """Validate the minimum local metadata required before offline loading."""
    assert_project_model_dir(repository_root, model_dir)
    resolved = model_dir.resolve()
    if not (resolved / "config.json").is_file():
        raise FileNotFoundError("offline benchmark requires a complete local model with config.json")
    return resolved
