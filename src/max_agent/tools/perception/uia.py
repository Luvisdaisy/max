"""只读窗口发现与 UI Automation 观察工具。"""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes

from pydantic import BaseModel, Field

from max_agent.tools.base import (
    ToolContext,
    ToolFailureCode,
    ToolPermission,
    ToolPhase,
    ToolReceipt,
)


class ObserveWindowsInput(BaseModel):
    max_windows: int = Field(default=100, ge=1, le=500)


class ObserveUiElementsInput(BaseModel):
    process_id: int = Field(gt=0)
    max_elements: int = Field(default=100, ge=1, le=500)


class _ObserveTool:
    permission = ToolPermission.OBSERVE
    allowed_phases = frozenset({ToolPhase.TOOL, ToolPhase.OBSERVE_AFTER_ACTION})
    timeout_seconds = 15.0
    recoverable = True
    model_visible = True
    side_effect = False
    read_only = True


class ObserveWindowsTool(_ObserveTool):
    name = "observe_windows"
    description = "List visible top-level windows with stable process identity."
    input_model = ObserveWindowsInput

    def __init__(
        self, observer: Callable[[int], list[dict[str, object]]] | None = None
    ) -> None:
        self._observer = observer or _observe_windows

    def invoke(
        self, tool_input: ObserveWindowsInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        try:
            windows = self._observer(tool_input.max_windows)
        except Exception as error:
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.UNAVAILABLE,
                f"window discovery failed: {type(error).__name__}",
            )
        return ToolReceipt(tool_name=self.name, success=True, data={"windows": windows})


class ObserveUiElementsTool(_ObserveTool):
    name = "observe_ui_elements"
    description = "Read bounded UI Automation metadata for one process."
    input_model = ObserveUiElementsInput

    def __init__(
        self, observer: Callable[[int, int], list[dict[str, object]]] | None = None
    ) -> None:
        self._observer = observer or _observe_process

    def invoke(
        self, tool_input: ObserveUiElementsInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        try:
            elements = self._observer(tool_input.process_id, tool_input.max_elements)
        except Exception as error:
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.UNAVAILABLE,
                f"UI Automation failed: {type(error).__name__}",
            )
        return ToolReceipt(
            tool_name=self.name, success=True, data={"elements": elements}
        )


def _observe_process(process_id: int, max_elements: int) -> list[dict[str, object]]:
    from pywinauto import Application

    window = Application(backend="uia").connect(process=process_id).top_window()
    elements: list[dict[str, object]] = []
    for element in window.descendants()[:max_elements]:
        info = element.element_info
        rectangle = element.rectangle()
        item: dict[str, object] = {
            "id": f"{process_id}:{info.handle}:{info.control_id}",
            "name": info.name or "",
            "role": info.control_type or "",
            "bounds": {
                "left": rectangle.left,
                "top": rectangle.top,
                "width": rectangle.width(),
                "height": rectangle.height(),
            },
            "enabled": bool(element.is_enabled()),
            "focused": bool(element.has_keyboard_focus()),
        }
        if info.control_type in {"Edit", "Document", "Text"}:
            try:
                item["value"] = element.window_text()
            except Exception:
                pass
        elements.append(item)
    return elements


def foreground_window_identity() -> dict[str, object] | None:
    hwnd = int(ctypes.windll.user32.GetForegroundWindow())
    return _window_identity(hwnd) if hwnd else None


def _observe_windows(max_windows: int) -> list[dict[str, object]]:
    user32 = ctypes.windll.user32
    windows: list[dict[str, object]] = []
    foreground = int(user32.GetForegroundWindow())

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        if len(windows) >= max_windows:
            return False
        if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        identity = _window_identity(int(hwnd))
        if identity is None:
            return True
        rectangle = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rectangle)):
            return True
        windows.append(
            {
                **identity,
                "bounds": {
                    "left": rectangle.left,
                    "top": rectangle.top,
                    "width": rectangle.right - rectangle.left,
                    "height": rectangle.bottom - rectangle.top,
                },
                "foreground": int(hwnd) == foreground,
                "taskbar_visible": True,
            }
        )
        return True

    user32.EnumWindows(callback, 0)
    return windows


def _window_identity(hwnd: int) -> dict[str, object] | None:
    user32 = ctypes.windll.user32
    length = int(user32.GetWindowTextLengthW(hwnd))
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, len(title))
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    path = _process_path(int(process_id.value))
    if not process_id.value or not path:
        return None
    return {
        "hwnd": int(hwnd),
        "process_id": int(process_id.value),
        "executable_path": path,
        "title": title.value,
    }


def _process_path(process_id: int) -> str:
    kernel32 = ctypes.windll.kernel32
    process = kernel32.OpenProcess(0x1000, False, process_id)
    if not process:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
            process, 0, buffer, ctypes.byref(size)
        ):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(process)
