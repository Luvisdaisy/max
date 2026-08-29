"""CLI 与 vLLM 二进制定位：子命令解析、记录清理与查找顺序。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from max_gui.cli import _run_cleanup, build_parser
from max_gui.config import MissingVllmError, Settings
from max_gui.lifecycle import resolve_vllm_bin


def test_parser_default_and_subcommands() -> None:
    """无子命令、`tui --new` 与 `cleanup` 能解析；无 `--model` 或 `serve`。"""
    parser = build_parser()
    assert parser.parse_args([]).command is None
    assert parser.parse_args(["tui", "--new"]).new is True
    cleanup = parser.parse_args(["cleanup"])
    assert cleanup.command == "cleanup"
    with pytest.raises(SystemExit):
        parser.parse_args(["serve"])
    with pytest.raises(SystemExit):
        parser.parse_args(["cleanup", "--yes"])


def test_cleanup_removes_records_and_keeps_directories(settings: Settings, monkeypatch) -> None:
    """清理命令无需交互即可删除三类记录内容并保留目录。"""
    runs = settings.project_root / "artifacts" / "runs"
    directories = (settings.screenshots_dir, runs, settings.sessions_dir)
    for directory in directories:
        directory.mkdir(parents=True)
        (directory / "record.json").write_text("x", encoding="utf-8")
        (directory / "nested").mkdir()
        (directory / "nested" / "detail.json").write_text("x", encoding="utf-8")
    monkeypatch.setattr("builtins.input", lambda _prompt: pytest.fail("cleanup 不应读取输入"))

    assert _run_cleanup(settings) == 0
    assert all(directory.is_dir() and not any(directory.iterdir()) for directory in directories)


def test_cleanup_failure_returns_nonzero(settings: Settings, monkeypatch) -> None:
    """单个条目删除失败时返回非零，同时继续处理其他目录。"""
    target = settings.sessions_dir / "blocked.json"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")
    original_unlink = Path.unlink

    def fail_one(path: Path, *args, **kwargs):
        if path == target:
            raise OSError("blocked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_one)
    assert _run_cleanup(settings) == 1
    assert target.is_file()


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


def test_benchmark_task_count_is_not_a_cli_argument() -> None:
    """评测规模仅能从首页选择，CLI 不接受数字位置参数。"""
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--benchmark", "10"])


def test_benchmark_flag_remains_available_from_max_gui_entrypoint() -> None:
    """原有 `max-gui --benchmark` 参数组合仍由顶层解析器接受。"""
    parser = build_parser()
    args = parser.parse_args(["--benchmark"])
    assert args.benchmark is True and args.command is None


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
