"""CLI 与 vLLM 启动：参数解析、缺权重提示、二进制查找顺序。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from max_gui.cli import build_parser
from max_gui.config import (
    MissingVllmError,
    MissingWeightsError,
    ServeNotAllowedError,
    Settings,
    require_weights,
)
from max_gui.lifecycle import _serve_command, resolve_vllm_bin, serve_model


def test_parser_default_and_subcommands() -> None:
    """无子命令、`tui --new`、`serve` 能解析；无 `--model`。"""
    parser = build_parser()
    assert parser.parse_args([]).command is None
    assert parser.parse_args(["tui", "--new"]).new is True
    serve = parser.parse_args(["serve"])
    assert serve.command == "serve"


def test_download_subcommand_removed() -> None:
    """`download` 不再是受支持的子命令。"""
    parser = build_parser()
    try:
        parser.parse_args(["download"])
    except SystemExit:
        return
    raise AssertionError("expected SystemExit for removed download command")


def test_model_flag_removed() -> None:
    """`--model` 不再作为 CLI 开关。"""
    parser = build_parser()
    try:
        parser.parse_args(["--model", "qwen3.5-2b"])
    except SystemExit:
        return
    raise AssertionError("expected SystemExit for removed --model")


def test_missing_weights_includes_path_not_download(settings: Settings, tmp_path: Path) -> None:
    """缺权重时错误信息包含目录路径，不含 download 命令。"""
    settings.model_name = "qwen3.5-2b"
    settings.model_root = tmp_path / "empty-models"
    settings.model_root.mkdir()
    try:
        require_weights(settings)
    except MissingWeightsError as exc:
        message = str(exc)
        assert "qwen3.5-2b" in message
        assert "download" not in message
        return
    raise AssertionError("expected MissingWeightsError")


def test_serve_rejected_for_modelscope(settings: Settings) -> None:
    """`modelscope` 下 `serve_model` 拒绝启动。"""
    settings.provider = "modelscope"
    settings.model_name = "Qwen/Qwen3.8-27B"
    try:
        serve_model(settings)
    except ServeNotAllowedError as exc:
        assert "local" in str(exc)
        assert ".env" in str(exc)
        return
    raise AssertionError("expected ServeNotAllowedError")


def test_serve_command_uses_resolved_binary(settings: Settings, tmp_path: Path) -> None:
    """`vllm serve` 使用指定二进制，不含 `python -m`。"""
    binary = tmp_path / "vllm"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    command = _serve_command(settings, settings.model_path, vllm_bin=binary)
    assert command[0] == str(binary)
    assert command[1] == "serve"
    assert str(settings.model_path) in command
    assert "--max-model-len" in command
    assert "--enable-auto-tool-choice" in command
    assert "--tool-call-parser" in command
    assert settings.model_name in command
    assert "python" not in Path(command[0]).name
    assert "-m" not in command


def test_resolve_vllm_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`MAX_GUI_VLLM` 指向可执行文件时优先采用。"""
    binary = tmp_path / "custom-vllm"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setenv("MAX_GUI_VLLM", str(binary))
    assert resolve_vllm_bin() == binary


def test_resolve_vllm_from_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """无环境变量且 PATH 没有时，使用传入的默认路径。"""
    monkeypatch.delenv("MAX_GUI_VLLM", raising=False)
    monkeypatch.setattr("max_gui.lifecycle.shutil.which", lambda _name: None)
    binary = tmp_path / "vllm"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    assert resolve_vllm_bin(default=binary) == binary


def test_resolve_vllm_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """找不到二进制时提示激活 venv 或设置 `MAX_GUI_VLLM`。"""
    monkeypatch.delenv("MAX_GUI_VLLM", raising=False)
    monkeypatch.setattr("max_gui.lifecycle.shutil.which", lambda _name: None)
    with pytest.raises(MissingVllmError) as exc:
        resolve_vllm_bin(default=tmp_path / "missing")
    assert "source ~/.venv-vllm-metal/bin/activate" in str(exc.value)
    assert "MAX_GUI_VLLM" in str(exc.value)
    assert os.getenv("MAX_GUI_VLLM") is None
