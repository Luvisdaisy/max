from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def assert_project_model_dir(repository_root: Path, model_dir: Path) -> None:
    """Require every model to live under the repository-root ``model`` tree."""
    expected_root = (repository_root / "model").resolve()
    resolved_model_dir = model_dir.resolve()
    try:
        resolved_model_dir.relative_to(expected_root)
    except ValueError:
        raise ValueError("model directory is outside the repository model tree") from None


@dataclass(frozen=True, slots=True)
class ModelConfig:
    model_id: str
    revision: str
    model_dir: Path

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id must not be empty")
        if not self.revision.strip():
            raise ValueError("revision must not be empty")
