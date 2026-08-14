from __future__ import annotations

from pathlib import Path

import pytest

from max_gui.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    workspace = tmp_path / "work"
    workspace.mkdir()
    sessions = tmp_path / "artifacts" / "sessions"
    model_root = tmp_path / "model"
    (model_root / "qwen3.5-2b").mkdir(parents=True)
    (model_root / "qwen3.5-2b" / "model.safetensors").write_bytes(b"x")
    return Settings(
        base_url="http://127.0.0.1:9/v1",
        model_alias="qwen3.5-2b",
        project_root=tmp_path,
        workspace=workspace,
        sessions_dir=sessions,
        screenshots_dir=tmp_path / "artifacts" / "screenshots",
        model_root=model_root,
        max_iterations=3,
        max_image_edge=64,
        max_image_bytes=20_000,
        tool_timeout=1.0,
    )
