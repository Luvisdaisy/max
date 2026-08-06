from __future__ import annotations

import os
from pathlib import Path


def configure_hf_modules_cache(artifact_root: Path) -> Path:
    """Route Transformers dynamic modules to a writable ignored directory."""
    cache_dir = artifact_root / "hf_modules"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_MODULES_CACHE"] = str(cache_dir)
    return cache_dir
