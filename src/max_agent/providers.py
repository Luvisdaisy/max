from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ModelProvider(Protocol):
    """Minimal local-only contract for future perception and planning modules."""

    def load(self, model_dir: Path) -> object: ...

    def infer_single_image(self, model: object, image_path: Path, prompt: str) -> dict[str, object]: ...
