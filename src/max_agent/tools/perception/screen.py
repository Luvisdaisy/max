"""屏幕观察工具：在显式监视器索引下返回内存图像与显示元数据。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

from max_agent.tools.base import ToolFailureCode, ToolReceipt


class ObserveScreenInput(BaseModel):
    monitor_index: int = Field(default=0, ge=0)


class ObserveScreenTool:
    """封装可替换的截屏函数，便于测试并限制观察范围。"""

    name = "observe_screen"
    description = "Capture one monitor as an in-memory image."
    read_only = True
    input_model = ObserveScreenInput

    def __init__(self, capture: Callable[[int], dict[str, Any]] | None = None) -> None:
        self._capture = capture or _capture_monitor

    def invoke(self, tool_input: ObserveScreenInput) -> ToolReceipt:
        try:
            captured = self._capture(tool_input.monitor_index)
        except (IndexError, ValueError) as error:
            return ToolReceipt.failure(
                self.name, ToolFailureCode.UNAVAILABLE, str(error)
            )
        return ToolReceipt(
            tool_name=self.name,
            success=True,
            data={
                "image": captured["image"],
                "width": captured["width"],
                "height": captured["height"],
                "bounds": captured["bounds"],
                "dpi": captured["dpi"],
            },
        )


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
