"""通过官方 ModelScope CLI 将受支持模型下载到仓库受管目录。"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from .config import ModelConfig, assert_project_model_dir

SnapshotDownload = Callable[..., str]


QWEN35_MODEL_ID = "Qwen/Qwen3.5-4B"


def qwen35_model_dir(repository_root: Path) -> Path:
    """返回唯一允许的 Qwen3.5-4B 本地下载目录。"""
    return repository_root / "model" / "Qwen" / "Qwen3.5-4B"


def download_qwen35_model(
    repository_root: Path, runner: Callable[[list[str]], None]
) -> Path:
    """经官方 ModelScope CLI 下载模型，并先校验目标目录安全边界。"""
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
    """以失败即抛异常的方式执行外部 ModelScope 命令。"""
    subprocess.run(command, check=True)


def validate_model_metadata(
    config: ModelConfig, repository_root: Path, model_file_download: SnapshotDownload
) -> Path:
    """在完整下载前仅获取配置元数据，避免隐式拉取权重。"""
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
