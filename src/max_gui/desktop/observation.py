"""只读桌面身份观察。

对外入口 `observe_desktop_identity` 只读取前台应用和窗口信息，缺少平台能力或权限时
返回显式未知状态。该模块绝不调用聚焦、点击、输入等辅助功能动作。
"""

from __future__ import annotations

import platform
from typing import Any


def observe_desktop_identity() -> dict[str, Any]:
    """读取当前前台应用、窗口、焦点和弹窗的最小观察结果。

    返回：
        始终包含四个身份字段与 `observation_status` 的字典。非 macOS、依赖不可用、
        或读取失败时各身份字段均为未知值。

    副作用：
        无；只读取系统公开窗口列表与工作区信息。
    """
    unknown = _unknown_snapshot()
    if platform.system() != "Darwin":
        unknown["observation_status"] = "unsupported_platform"
        return unknown
    try:
        import AppKit
        import Quartz
    except ImportError:
        unknown["observation_status"] = "observation_unavailable"
        return unknown
    try:
        app = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            unknown["observation_status"] = "frontmost_app_unavailable"
            return unknown
        process_id = int(app.processIdentifier())
        app_name = str(app.localizedName() or "").strip() or None
        unknown["active_app"] = {
            "id": str(process_id),
            "name": app_name,
            "role": "application",
        }
        window = _frontmost_window(Quartz, process_id)
        if window is not None:
            unknown["active_window"] = window
        unknown["observation_status"] = "ok"
    except Exception:
        unknown["observation_status"] = "observation_failed"
    return unknown


def _frontmost_window(quartz: Any, process_id: int) -> dict[str, str | None] | None:
    """从窗口服务器的只读列表取前台应用首个正常层级窗口。"""
    options = quartz.kCGWindowListOptionOnScreenOnly | quartz.kCGWindowListExcludeDesktopElements
    windows = quartz.CGWindowListCopyWindowInfo(options, quartz.kCGNullWindowID) or []
    for item in windows:
        if int(item.get(quartz.kCGWindowOwnerPID, -1)) != process_id:
            continue
        title = str(item.get(quartz.kCGWindowName) or "").strip() or None
        return {
            "id": str(item.get(quartz.kCGWindowNumber) or "") or None,
            "name": title,
            "role": "window",
        }
    return None


def _unknown_snapshot() -> dict[str, Any]:
    """构造四类身份均为未知的稳定结果。"""
    unknown = {"id": None, "name": None, "role": None}
    return {
        "active_app": dict(unknown),
        "active_window": dict(unknown),
        "focused_element": dict(unknown),
        "active_dialog": dict(unknown),
        "observation_status": "unknown",
    }
