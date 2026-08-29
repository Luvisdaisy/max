"""macOS Dock 的只读辅助功能发现。

本模块只读取 Dock 元素的标题与边界，绝不调用辅助功能动作；返回的候选仍必须
经现有 `mouse_move` 和截图核验链路执行。
"""

from __future__ import annotations

import platform
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DockCandidate:
    """一个可投影到截图的 Dock 应用观察结果。"""

    title: str
    x: float
    y: float
    width: float
    height: float


def find_dock_apps() -> tuple[list[DockCandidate], str]:
    """读取 macOS Dock 无障碍元素；返回候选和不含标题正文的状态码。

    返回：`(候选, 状态码)`。非 macOS、未授权或 API 不可用时返回空列表；不抛异常。
    """
    if platform.system() != "Darwin":
        return [], "unsupported_platform"
    try:
        import AppKit
        import ApplicationServices
    except ImportError:
        return [], "accessibility_unavailable"
    if not ApplicationServices.AXIsProcessTrusted():
        return [], "accessibility_not_trusted"
    try:
        apps = AppKit.NSWorkspace.sharedWorkspace().runningApplications()
        dock = next((item for item in apps if item.localizedName() == "Dock"), None)
        if dock is None:
            return [], "dock_not_found"
        element = ApplicationServices.AXUIElementCreateApplication(dock.processIdentifier())
        error, children = ApplicationServices.AXUIElementCopyAttributeValue(
            element, "AXChildren", None
        )
        if error != 0 or not children:
            return [], "dock_elements_unavailable"
        candidates: list[DockCandidate] = []
        for child in children:
            _, title = ApplicationServices.AXUIElementCopyAttributeValue(child, "AXTitle", None)
            _, position = ApplicationServices.AXUIElementCopyAttributeValue(
                child, "AXPosition", None
            )
            _, size = ApplicationServices.AXUIElementCopyAttributeValue(child, "AXSize", None)
            if not title or position is None or size is None:
                continue
            candidates.append(
                DockCandidate(
                    title=str(title),
                    x=float(position.x),
                    y=float(position.y),
                    width=float(size.width),
                    height=float(size.height),
                )
            )
        return candidates, "ok"
    except Exception:
        return [], "dock_read_failed"
