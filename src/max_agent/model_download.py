from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from .config import ModelConfig, assert_project_model_dir

SnapshotDownload = Callable[..., str]


QWEN35_MODEL_ID = "Qwen/Qwen3.5-4B"


def qwen35_model_dir(repository_root: Path) -> Path:
    return repository_root / "model" / "Qwen" / "Qwen3.5-4B"


def download_qwen35_model(
    repository_root: Path, runner: Callable[[list[str]], None]
) -> Path:
    """Download the selected Qwen model through the official ModelScope CLI."""
    destination = qwen35_model_dir(repository_root)
    assert_project_model_dir(repository_root, destination)
    runner(
        [
            "modelscope",
            "download",
            "--model",
            QWEN35_MODEL_ID,
            "--local_dir",
            str(destination),
        ]
    )
    return destination


def run_modelscope_cli(command: list[str]) -> None:
    subprocess.run(command, check=True)


def validate_model_metadata(
    config: ModelConfig, repository_root: Path, model_file_download: SnapshotDownload
) -> Path:
    """Fetch only model metadata before an explicit full-weight download."""
    assert_project_model_dir(repository_root, config.model_dir)
    downloaded = model_file_download(
        model_id=config.model_id,
        revision=config.revision,
        file_path="config.json",
        cache_dir=str(config.model_dir),
    )
    return Path(downloaded)


def modelscope_snapshot_download(**kwargs: str) -> str:
    from modelscope import snapshot_download

    return str(snapshot_download(**kwargs))
