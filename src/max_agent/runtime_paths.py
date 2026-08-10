"""配置运行时生成文件的可写且受 Git 忽略的存放位置。"""

from __future__ import annotations

import os
from pathlib import Path


def configure_hf_modules_cache(artifact_root: Path) -> Path:
    """将 Transformers 动态模块缓存定向到可写的归档目录。"""
    cache_dir = artifact_root / "hf_modules"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["HF_MODULES_CACHE"] = str(cache_dir)
    return cache_dir
