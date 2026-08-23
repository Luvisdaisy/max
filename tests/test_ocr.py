"""OCR 工具：路径范围、懒启动、vLLM / transformers 回退与跳过。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from PIL import Image

from max_gui.config import DEFAULT_OCR_MODEL, Settings
from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.inference.ocr import (
    OCR_SKIP_MESSAGE,
    OcrRuntime,
    ocr_serve_command,
    shutdown_owned_ocr,
)
from max_gui.inference.spotting import SpottingParseError, parse_spotting
from max_gui.lifecycle import _serve_command
from max_gui.tools.desktop import clear_desktop_context
from max_gui.tools.protocol import ToolResult
from max_gui.tools.registry import DenyGate, build_default_registry


class _DummyProc:
    def __init__(self) -> None:
        self.code: int | None = None

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.code = 0

    def kill(self) -> None:
        self.code = 0

    def wait(self, timeout: float | None = None) -> int:
        self.code = 0
        return 0


def _write_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color="white").save(path)
    return path


def _registry(settings: Settings, runtime: OcrRuntime):
    clear_desktop_context()
    return build_default_registry(
        settings, desktop=FakeDesktopBackend(), ocr=runtime, gate=DenyGate()
    )


def test_parse_spotting_json_and_lines() -> None:
    """JSON 与行文本都能抽出框；空文本失败。"""
    boxes = parse_spotting('[{"text": "确定", "bbox": [10, 20, 50, 40]}]')
    assert boxes[0].text == "确定"
    assert boxes[0].x1 == 10 and boxes[0].y2 == 40
    quad = parse_spotting("取消\t[[0, 0], [8, 0], [8, 4], [0, 4]]")
    assert quad[0].text == "取消"
    assert quad[0].x2 == 8 and quad[0].y2 == 4
    line = parse_spotting("保存 [1, 2, 3, 4]")
    assert line[0].text == "保存" and line[0].x1 == 1
    try:
        parse_spotting("没有任何坐标")
    except SpottingParseError:
        pass
    else:
        raise AssertionError("expected SpottingParseError")


async def test_ocr_registered_and_no_confirmation(settings: Settings) -> None:
    """默认表含 `ocr`，拒绝门也不拦截。"""
    runtime = OcrRuntime(
        settings,
        start_fn=_DummyProc,
        healthy_fn=_healthy_true,
        complete_fn=_async_text("识别到 确定"),
    )
    registry = _registry(settings, runtime)
    tool = registry.get("ocr")
    assert tool is not None
    assert tool.requires_confirmation is False
    assert "ocr" in {item["function"]["name"] for item in registry.schemas()}
    path = _write_png(settings.screenshots_dir / "shot.png")
    result = await registry.invoke("ocr", {"path": str(path)})
    assert result == "识别到 确定"
    assert not isinstance(result, ToolResult)


async def test_ocr_reads_workspace_and_rejects_escape(settings: Settings) -> None:
    """工作区图可读；逃出截图目录与工作区被拒绝且不启动。"""
    runtime = OcrRuntime(
        settings,
        start_fn=_DummyProc,
        healthy_fn=_healthy_true,
        complete_fn=_async_text("workspace-text"),
    )
    registry = _registry(settings, runtime)
    _write_png(settings.workspace / "ui.png")
    assert await registry.invoke("ocr", {"path": "ui.png"}) == "workspace-text"
    outside = settings.project_root / "secret.png"
    _write_png(outside)
    denied = await registry.invoke("ocr", {"path": str(outside)})
    assert "权限" in denied
    assert runtime.start_count == 0
    missing = await registry.invoke("ocr", {"path": "nope.png"})
    assert "不存在" in missing
    empty = await registry.invoke("ocr", {})
    assert "需要 path" in empty
    assert runtime.start_count == 0


async def test_ocr_vllm_success_skips_transformers(settings: Settings) -> None:
    """vLLM 成功时不走 transformers。"""
    called = {"tf": 0}

    async def transformers(_path: Path) -> str:
        called["tf"] += 1
        return "should-not"

    runtime = OcrRuntime(
        settings,
        start_fn=_DummyProc,
        healthy_fn=_healthy_true,
        complete_fn=_async_text("vllm-ok"),
        transformers_fn=transformers,
    )
    registry = _registry(settings, runtime)
    path = _write_png(settings.screenshots_dir / "a.png")
    assert await registry.invoke("ocr", {"path": str(path)}) == "vllm-ok"
    assert called["tf"] == 0


async def test_ocr_falls_back_then_skips(settings: Settings) -> None:
    """vLLM 失败走回退；两档都失败返回可跳过文案。"""

    async def boom_complete(_part: dict) -> str:
        raise RuntimeError("vllm down")

    runtime = OcrRuntime(
        settings,
        start_fn=_DummyProc,
        healthy_fn=_healthy_false,
        complete_fn=boom_complete,
        transformers_fn=_async_text("tf-ok"),
    )
    runtime.settings = settings
    # healthy stays false so ensure_server times out quickly
    settings.ocr_start_timeout = 0.05
    registry = _registry(settings, runtime)
    path = _write_png(settings.screenshots_dir / "b.png")
    result = await registry.invoke("ocr", {"path": str(path)})
    assert "tf-ok" in result
    assert "transformers" in result

    async def boom_tf(_path: Path) -> str:
        raise RuntimeError("tf down")

    runtime2 = OcrRuntime(
        settings,
        start_fn=_DummyProc,
        healthy_fn=_healthy_false,
        complete_fn=boom_complete,
        transformers_fn=boom_tf,
    )
    registry2 = _registry(settings, runtime2)
    skipped = await registry2.invoke("ocr", {"path": str(path)})
    assert skipped == OCR_SKIP_MESSAGE


async def test_ocr_reuses_started_server(settings: Settings) -> None:
    """第一次启动后第二次不拉第二个进程。"""
    started = {"n": 0}
    ready = {"ok": False}

    def start() -> _DummyProc:
        started["n"] += 1
        ready["ok"] = True
        return _DummyProc()

    async def healthy() -> bool:
        return ready["ok"]

    runtime = OcrRuntime(
        settings,
        start_fn=start,
        healthy_fn=healthy,
        complete_fn=_async_text("once"),
    )
    registry = _registry(settings, runtime)
    path = _write_png(settings.screenshots_dir / "c.png")
    first, second = await asyncio.gather(
        registry.invoke("ocr", {"path": str(path)}),
        registry.invoke("ocr", {"path": str(path)}),
    )
    assert first == "once" and second == "once"
    third = await registry.invoke("ocr", {"path": str(path)})
    assert third == "once"
    assert started["n"] == 1
    assert runtime.start_count == 1


def test_main_serve_does_not_start_ocr(settings: Settings, tmp_path: Path) -> None:
    """`max-gui serve` 命令只加载主模型，不含 OCR 权重与 trust-remote-code。"""
    binary = tmp_path / "vllm"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    command = _serve_command(settings, settings.model_path, vllm_bin=binary)
    joined = " ".join(command)
    assert DEFAULT_OCR_MODEL not in joined
    assert "paddleocr" not in joined
    assert "--trust-remote-code" not in command
    assert "--tool-call-parser" in command
    ocr_cmd = ocr_serve_command(settings, vllm_bin=binary)
    assert str(settings.ocr_model_path) in ocr_cmd
    assert "--trust-remote-code" in ocr_cmd
    assert "--no-enable-prefix-caching" in ocr_cmd
    assert "--max-model-len" in ocr_cmd
    assert str(settings.max_model_len) in ocr_cmd
    assert "--tool-call-parser" not in ocr_cmd
    assert "8001" in ocr_cmd


def test_shutdown_only_kills_owned(settings: Settings) -> None:
    """未由本运行时拉起的健康实例不会在 shutdown 时被杀。"""
    proc = _DummyProc()
    runtime = OcrRuntime(settings, start_fn=lambda: proc, healthy_fn=_healthy_true)
    runtime.shutdown()
    assert proc.code is None
    runtime2 = OcrRuntime(
        settings,
        start_fn=lambda: proc,
        healthy_fn=_healthy_false,
    )
    runtime2.settings = settings
    runtime2.settings.ocr_start_timeout = 0.0
    # owned after start
    runtime2._start_server()
    assert proc.code is None
    shutdown_owned_ocr()
    assert proc.code == 0


async def _healthy_true() -> bool:
    return True


async def _healthy_false() -> bool:
    return False


def _async_text(text: str):
    async def inner(_arg: object) -> str:
        return text

    return inner
