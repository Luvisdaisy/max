"""屏幕观察工具：截图只进入任务内存资源，不默认落盘。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

from max_agent.tools.base import (
    ToolContext,
    ToolFailureCode,
    ToolPermission,
    ToolPhase,
    ToolReceipt,
)


class ObserveScreenInput(BaseModel):
    monitor_index: int = Field(default=0, ge=0)


class ObserveScreenTool:
    """封装可替换截屏函数，并在运行时上下文存在时返回资源引用。"""

    name = "observe_screen"
    description = "Capture one monitor into task-scoped memory."
    permission = ToolPermission.OBSERVE
    allowed_phases = frozenset({ToolPhase.TOOL, ToolPhase.OBSERVE_AFTER_ACTION})
    timeout_seconds = 15.0
    recoverable = True
    model_visible = True
    side_effect = False
    read_only = True
    input_model = ObserveScreenInput

    def __init__(
        self,
        capture: Callable[[int], dict[str, Any]] | None = None,
        foreground: Callable[[], dict[str, object] | None] | None = None,
    ) -> None:
        self._capture = capture or _capture_monitor
        self._foreground = foreground or _foreground_window

    def invoke(
        self, tool_input: ObserveScreenInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        try:
            captured = self._capture(tool_input.monitor_index)
        except (IndexError, ValueError) as error:
            return ToolReceipt.failure(
                self.name, ToolFailureCode.UNAVAILABLE, str(error)
            )
        image = captured["image"]
        data: dict[str, object] = {
            "width": captured["width"],
            "height": captured["height"],
            "bounds": captured["bounds"],
            "dpi": captured["dpi"],
            "captured_at": time.time(),
            "foreground_window": self._foreground(),
        }
        if context is None:
            data["image"] = image
        else:
            data["image_ref"] = context.resources.put(
                context.task_id, "image", image
            ).model_dump()
        return ToolReceipt(tool_name=self.name, success=True, data=data)


def _capture_monitor(monitor_index: int) -> dict[str, Any]:
    import mss

    with mss.mss() as capture:
        if monitor_index >= len(capture.monitors):
            raise IndexError(f"monitor {monitor_index} is unavailable")
        monitor = capture.monitors[monitor_index]
        frame = capture.grab(monitor)
    image = Image.frombytes("RGB", frame.size, frame.bgra, "raw", "BGRX")
    return {
        "image": image,
        "width": frame.width,
        "height": frame.height,
        "bounds": {
            key: int(monitor[key]) for key in ("left", "top", "width", "height")
        },
        "dpi": _system_dpi(),
    }


def _system_dpi() -> int | None:
    try:
        import ctypes

        return int(ctypes.windll.user32.GetDpiForSystem())
    except (AttributeError, OSError):
        return None


def _foreground_window() -> dict[str, object] | None:
    """尽力读取前台窗口稳定身份；失败时截图仍然有效。"""
    try:
        from max_agent.tools.perception.uia import foreground_window_identity

        return foreground_window_identity()
    except (OSError, RuntimeError, ValueError):
        return None
