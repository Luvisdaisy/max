"""共享夹具：在临时目录构造带占位权重的 `Settings`。"""

from __future__ import annotations

from pathlib import Path

import pytest

from max_gui.config import Settings


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例开始时清掉推理相关环境变量，避免 `.env` 载入污染后续测试。"""
    for key in (
        "MAX_PROVIDER",
        "MAX_PROVIDER_KEY",
        "MAX_MODELSCOPE_KEY",
        "MAX_DASHSCOPE_KEY",
        "MAX_OPENROUTER_KEY",
        "OPENROUTER_API_KEY",
        "MODEL_NAME",
        "MAX_GUI_BASE_URL",
        "MAX_DASHSCOPE_WORKSPACE",
        "MAX_BAILIAN_WORKSPACE",
        "MAX_GUI_MODEL",
        "MAX_GUI_API_KEY",
        "MAX_GUI_INFERENCE_MAX_RETRIES",
        "MODELSCOPE_SDK_TOKEN",
        "DASHSCOPE_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """隔离工作区、会话目录与假 `qwen3.5-2b` 权重，推理端口指向不可达地址。"""
    workspace = tmp_path / "work"
    workspace.mkdir()
    sessions = tmp_path / "artifacts" / "sessions"
    model_root = tmp_path / "model"
    (model_root / "qwen3.5-2b").mkdir(parents=True)
    (model_root / "qwen3.5-2b" / "model.safetensors").write_bytes(b"x")
    return Settings(
        base_url="http://127.0.0.1:9/v1",
        model_name="qwen3.5-2b",
        project_root=tmp_path,
        workspace=workspace,
        sessions_dir=sessions,
        screenshots_dir=tmp_path / "artifacts" / "screenshots",
        model_root=model_root,
        max_iterations=3,
        max_image_edge=64,
        max_image_bytes=20_000,
        tool_timeout=1.0,
        inference_max_retries=0,
    )
