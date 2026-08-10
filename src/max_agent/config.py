"""模型配置与仓库内模型目录的安全边界。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def assert_project_model_dir(repository_root: Path, model_dir: Path) -> None:
    """拒绝仓库 `model/` 目录外的模型路径，避免读取未受管控的位置。"""
    expected_root = (repository_root / "model").resolve()
    resolved_model_dir = model_dir.resolve()
    try:
        resolved_model_dir.relative_to(expected_root)
    except ValueError:
        raise ValueError(
            "model directory is outside the repository model tree"
        ) from None


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """下载模型元数据所需的稳定标识、版本与本地目标目录。"""

    model_id: str
    revision: str
    model_dir: Path

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id must not be empty")
        if not self.revision.strip():
            raise ValueError("revision must not be empty")
