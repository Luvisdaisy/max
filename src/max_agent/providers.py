"""定义本地模型提供方的最小协议，隔离具体推理实现。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ModelProvider(Protocol):
    """供感知与编排模块使用的最小本地模型协议。"""

    def load(self, model_dir: Path) -> object: ...

    def infer_single_image(
        self, model: object, image_path: Path, prompt: str
    ) -> dict[str, object]: ...
