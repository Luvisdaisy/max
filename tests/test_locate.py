"""界面定位工具：默认路径、截断 40、越权、失败跳过与命中表。"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from max_gui.config import DEFAULT_OMNIPARSER_DIR, Settings
from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.inference.images import prepare_image
from max_gui.inference.omniparser import (
    LOCATE_EMPTY_MESSAGE,
    LOCATE_SKIP_MESSAGE,
    DetectedBox,
    LocateRuntime,
    LocateUnavailable,
    shutdown_owned_locate,
)
from max_gui.inference.omniparser_worker import _find_detect_weights
from max_gui.tools.desktop import (
    active_locate_hits,
    clear_desktop_context,
    store_locate_hits,
)
from max_gui.tools.protocol import ToolResult
from max_gui.tools.registry import DenyGate, build_default_registry


class _DummyProc:
    """假子进程：记录是否被 terminate。"""

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


def _write_png(path: Path, size: tuple[int, int] = (64, 64)) -> Path:
    """写一张纯色 PNG。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color="white").save(path)
    return path


def _box(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    label: str = "icon",
    *,
    score: float = 1.0,
) -> DetectedBox:
    """构造原图像素框。"""
    return DetectedBox(x1=x1, y1=y1, x2=x2, y2=y2, label=label, role="icon", score=score)


def _parse_boxes(boxes: list[DetectedBox]):
    """把固定框列表做成 parse_fn。"""

    async def inner(_path: Path) -> list[DetectedBox]:
        return list(boxes)

    return inner


def _registry(settings: Settings, runtime: LocateRuntime):
    """装配带假桌面与注入定位运行时的注册表。"""
    clear_desktop_context()
    return build_default_registry(
        settings, desktop=FakeDesktopBackend(), locate=runtime, gate=DenyGate()
    )


def test_omniparser_default_dir_and_detect_weights(settings: Settings) -> None:
    """默认权重目录为 omniparserv2，并能找到 icon_detect/model.pt。"""
    assert DEFAULT_OMNIPARSER_DIR == "omniparserv2"
    assert settings.omniparser_model_path.name == "omniparserv2"
    detect = settings.omniparser_model_path / "icon_detect"
    detect.mkdir(parents=True)
    weights = detect / "model.pt"
    weights.write_bytes(b"x")
    assert _find_detect_weights(settings.omniparser_model_path) == weights


async def test_locate_draws_boxes_and_default_path(settings: Settings) -> None:
    """定位成功画编号，省略 path 时用当前截图。"""
    runtime = LocateRuntime(settings, parse_fn=_parse_boxes([_box(0, 0, 16, 16, "确定")]))
    registry = _registry(settings, runtime)
    tool = registry.get("locate")
    assert tool is not None
    assert tool.requires_confirmation is False
    assert "locate" in {item["function"]["name"] for item in registry.schemas()}
    assert "ocr_locate" not in {item["function"]["name"] for item in registry.schemas()}
    shot = await registry.invoke("screenshot", {})
    assert isinstance(shot, ToolResult)
    result = await registry.invoke("locate", {})
    assert isinstance(result, ToolResult)
    payload = json.loads(result.text)
    assert payload["items"][0]["label"] == "确定"
    assert payload["items"][0]["id"] == 1
    assert payload["coordinate_space"] == "view"
    assert result.images and result.images[0].is_file()
    assert 1 in active_locate_hits()


async def test_current_retina_screenshot_target_id_uses_logical_center(settings: Settings) -> None:
    """当前 2 倍截图的框中心会回映射到桌面逻辑像素，而非物理像素。"""
    backend = FakeDesktopBackend()
    runtime = LocateRuntime(settings, parse_fn=_parse_boxes([_box(1400, 800, 1480, 1000, "按钮")]))
    clear_desktop_context()
    registry = build_default_registry(settings, desktop=backend, locate=runtime, gate=DenyGate())
    await registry.invoke("screenshot", {})
    located = await registry.invoke("locate", {})
    assert isinstance(located, ToolResult)
    await registry.invoke("mouse_move", {"target_id": 1})
    assert backend.mouse == (720, 450)


async def test_locate_caps_at_forty_boxes(settings: Settings) -> None:
    """观察专用图片超过 40 个框时只编号 1 到 40，且不留下可执行命中。"""
    boxes = [_box(i * 10, 0, i * 10 + 8, 8, str(i), score=float(100 - i)) for i in range(50)]
    runtime = LocateRuntime(settings, parse_fn=_parse_boxes(boxes))
    registry = _registry(settings, runtime)
    path = _write_png(settings.screenshots_dir / "many.png", (520, 20))
    result = await registry.invoke("locate", {"path": str(path)})
    assert isinstance(result, ToolResult)
    payload = json.loads(result.text)
    assert len(payload["items"]) == 40
    assert payload["items"][-1]["id"] == 40
    assert payload["coordinate_space"] == "image"
    assert payload["observation_only"] is True
    assert active_locate_hits() == {}


async def test_historical_retina_image_is_observation_only(settings: Settings) -> None:
    """历史 2 倍物理像素图不生成可点击编号，避免把物理像素当逻辑像素。"""
    runtime = LocateRuntime(settings, parse_fn=_parse_boxes([_box(1400, 800, 1480, 880, "按钮")]))
    registry = _registry(settings, runtime)
    await registry.invoke("screenshot", {})
    store_locate_hits({9: (10, 20)})
    historical = _write_png(settings.screenshots_dir / "history-retina.png", (2880, 1800))
    result = await registry.invoke("locate", {"path": str(historical)})
    assert isinstance(result, ToolResult)
    payload = json.loads(result.text)
    assert payload["coordinate_space"] == "image"
    assert payload["observation_only"] is True
    assert "logical" not in payload["items"][0]
    assert active_locate_hits() == {}
    moved = await registry.invoke("mouse_move", {"target_id": 1})
    assert "请先调用 locate" in moved


async def test_overlay_copy_is_observation_only(settings: Settings) -> None:
    """当前截图生成的带框副本不继承原截图的桌面坐标帧。"""
    runtime = LocateRuntime(settings, parse_fn=_parse_boxes([_box(0, 0, 16, 16, "按钮")]))
    registry = _registry(settings, runtime)
    await registry.invoke("screenshot", {})
    current = await registry.invoke("locate", {})
    assert isinstance(current, ToolResult)
    copied = await registry.invoke("locate", {"path": str(current.images[0])})
    assert isinstance(copied, ToolResult)
    payload = json.loads(copied.text)
    assert payload["observation_only"] is True
    assert active_locate_hits() == {}


async def test_locate_overlay_coordinates_match_encoded_image(settings: Settings) -> None:
    """框图因字节上限缩小时，JSON 视图坐标仍匹配最终发送给模型的尺寸。"""
    settings.max_image_edge = 64
    settings.max_image_bytes = 400
    runtime = LocateRuntime(settings, parse_fn=_parse_boxes([_box(0, 0, 32, 32, "按钮")]))
    registry = _registry(settings, runtime)
    await registry.invoke("screenshot", {})
    result = await registry.invoke("locate", {})
    assert isinstance(result, ToolResult)
    payload = json.loads(result.text)
    encoded = prepare_image(
        result.images[0], max_edge=settings.max_image_edge, max_bytes=settings.max_image_bytes
    )
    item = payload["items"][0]
    assert encoded.width < 64
    assert item["view"]["x"] + item["view"]["w"] <= encoded.width
    assert item["view"]["y"] + item["view"]["h"] <= encoded.height


async def test_locate_rejects_remote_path_worker(settings: Settings) -> None:
    """远端 worker 不得收到主进程本地绝对路径。"""
    calls: list[Path] = []

    async def record(path: Path) -> list[DetectedBox]:
        calls.append(path)
        return [_box(0, 0, 16, 16)]

    settings.omniparser_base_url = "http://192.0.2.10:8002"
    registry = _registry(settings, LocateRuntime(settings, parse_fn=record))
    path = _write_png(settings.screenshots_dir / "remote.png")
    result = await registry.invoke("locate", {"path": str(path)})
    assert "仅支持本机 loopback" in result
    assert calls == []


async def test_locate_rejects_escape_and_skips(settings: Settings) -> None:
    """越权不调用解析；失败可跳过；空框可跳过。"""
    calls: list[Path] = []

    async def record(path: Path) -> list[DetectedBox]:
        calls.append(path)
        return [_box(0, 0, 8, 8)]

    runtime = LocateRuntime(settings, parse_fn=record)
    registry = _registry(settings, runtime)
    outside = settings.project_root / "secret.png"
    _write_png(outside)
    denied = await registry.invoke("locate", {"path": str(outside)})
    assert "权限" in denied
    assert calls == []

    async def boom(_path: Path) -> list[DetectedBox]:
        raise LocateUnavailable("down")

    failing = LocateRuntime(settings, parse_fn=boom)
    registry = _registry(settings, failing)
    path = _write_png(settings.screenshots_dir / "down.png")
    skipped = await registry.invoke("locate", {"path": str(path)})
    assert skipped.startswith(LOCATE_SKIP_MESSAGE)
    assert "down" in skipped

    empty = LocateRuntime(settings, parse_fn=_parse_boxes([]))
    registry = _registry(settings, empty)
    none = await registry.invoke("locate", {"path": str(path)})
    assert none == LOCATE_EMPTY_MESSAGE


async def test_locate_skip_includes_startup_reason(settings: Settings) -> None:
    """worker 立刻退出时跳过文案含退出码与日志摘录。"""

    class DeadProc:
        def poll(self) -> int:
            return 1

        def terminate(self) -> None:
            return None

        def kill(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            return 1

    settings.omniparser_start_timeout = 0.05
    log = settings.project_root / "artifacts" / "logs" / "omniparser.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("failed to load OmniParser: No module named 'ultralytics'\n", encoding="utf-8")
    runtime = LocateRuntime(settings, start_fn=lambda: DeadProc(), healthy_fn=_healthy_false)
    registry = _registry(settings, runtime)
    path = _write_png(settings.screenshots_dir / "fail.png")
    skipped = await registry.invoke("locate", {"path": str(path)})
    assert LOCATE_SKIP_MESSAGE in skipped
    assert "退出码 1" in skipped
    assert "ultralytics" in skipped
    assert "omniparser.log" in skipped


async def test_ocr_locate_is_unknown(settings: Settings) -> None:
    """已移除的 `ocr_locate` 按未知工具处理。"""
    runtime = LocateRuntime(settings, parse_fn=_parse_boxes([]))
    registry = _registry(settings, runtime)
    result = await registry.invoke("ocr_locate", {"path": "shot.png"})
    assert "未知工具" in result


async def test_screenshot_clears_hits_move_keeps_them(settings: Settings) -> None:
    """模型截图与点击后清空编号；移鼠核验截图保留。"""
    runtime = LocateRuntime(settings, parse_fn=_parse_boxes([_box(0, 0, 16, 16, "A")]))
    registry = _registry(settings, runtime)
    await registry.invoke("screenshot", {})
    located = await registry.invoke("locate", {})
    assert isinstance(located, ToolResult)
    assert 1 in active_locate_hits()
    moved = await registry.invoke("mouse_move", {"target_id": 1})
    assert "定位编号" in (moved.text if isinstance(moved, ToolResult) else moved)
    assert 1 in active_locate_hits()
    await registry.invoke("screenshot", {})
    missing = await registry.invoke("mouse_move", {"target_id": 1})
    assert "没有 id=1" in missing
    store_locate_hits({1: (10, 10)})
    await registry.invoke("mouse_move", {"x": 2, "y": 2})
    await registry.invoke("mouse_click", {})
    gone = await registry.invoke("mouse_move", {"target_id": 1})
    assert "没有 id=1" in gone


def test_shutdown_only_kills_owned_locate(settings: Settings) -> None:
    """未由本运行时拉起的实例不会在 shutdown 时被杀。"""
    proc = _DummyProc()
    runtime = LocateRuntime(settings, start_fn=lambda: proc, healthy_fn=_healthy_true)
    runtime.shutdown()
    assert proc.code is None
    runtime2 = LocateRuntime(
        settings,
        start_fn=lambda: proc,
        healthy_fn=_healthy_false,
    )
    runtime2.settings.omniparser_start_timeout = 0.0
    runtime2._start_server()
    shutdown_owned_locate()
    assert proc.code == 0


async def _healthy_true() -> bool:
    return True


async def _healthy_false() -> bool:
    return False
