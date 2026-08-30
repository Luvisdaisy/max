"""macOS Dock 只读辅助功能适配层的隔离测试。

用最小 fake 模块覆盖权限、平台、元素读取和异常状态；测试不连接真实 Dock，也不执行 AX 动作。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

from max_gui.tools import dock


class _Point:
    """模拟辅助功能返回的屏幕坐标。"""

    x = 10
    y = 20


class _Size:
    """模拟辅助功能返回的元素尺寸。"""

    width = 30
    height = 40


def _fake_accessibility_modules(
    monkeypatch,
    *,
    trusted: bool = True,
    children: list[object] | None = None,
) -> list[str]:
    """注入只读 Dock 依赖并记录调用，避免测试触达真实系统辅助功能树。"""
    calls: list[str] = []

    class _Workspace:
        @staticmethod
        def sharedWorkspace():
            return _Workspace()

        def runningApplications(self):
            return [
                types.SimpleNamespace(localizedName=lambda: "Dock", processIdentifier=lambda: 7)
            ]

    class _AppKit:
        NSWorkspace = _Workspace

    def copy_attribute(_element, name, _parameter):
        calls.append(name)
        if name in {"AXPress", "AXPerformAction"}:
            raise AssertionError("适配层不应调用 AX 动作")
        if name == "AXChildren":
            return 0, children or []
        if name == "AXTitle":
            return 0, "Google Chrome"
        if name == "AXPosition":
            return 0, _Point()
        if name == "AXSize":
            return 0, _Size()
        return 1, None

    class _Accessibility:
        @staticmethod
        def AXIsProcessTrusted():
            return trusted

        @staticmethod
        def AXUIElementCreateApplication(_pid):
            calls.append("create")
            return object()

        AXUIElementCopyAttributeValue = staticmethod(copy_attribute)

    monkeypatch.setitem(sys.modules, "AppKit", _AppKit)
    monkeypatch.setitem(sys.modules, "ApplicationServices", _Accessibility)
    monkeypatch.setattr(dock.platform, "system", lambda: "Darwin")
    return calls


def test_find_dock_apps_reads_only_title_and_bounds(monkeypatch) -> None:
    """成功发现只读取标题、位置和尺寸，不调用任何 AX 动作。"""
    calls = _fake_accessibility_modules(monkeypatch, children=[object()])

    candidates, status = dock.find_dock_apps()

    assert status == "ok"
    assert [(item.title, item.x, item.y, item.width, item.height) for item in candidates] == [
        ("Google Chrome", 10, 20, 30, 40)
    ]
    assert calls == ["create", "AXChildren", "AXTitle", "AXPosition", "AXSize"]


def test_find_dock_apps_reports_unsupported_or_untrusted(monkeypatch) -> None:
    """非 macOS 与未授权环境分别返回稳定状态码，且不尝试读取元素。"""
    monkeypatch.setattr(dock.platform, "system", lambda: "Linux")
    assert dock.find_dock_apps() == ([], "unsupported_platform")

    _fake_accessibility_modules(monkeypatch, trusted=False)
    assert dock.find_dock_apps() == ([], "accessibility_not_trusted")


def test_dock_candidate_outside_frame_is_rejected(monkeypatch) -> None:
    """屏幕外 Dock 候选不能投影为当前截图的可执行定位结果。"""
    _fake_accessibility_modules(monkeypatch, children=[object()])
    from max_gui.tools.desktop import ViewFrame
    from max_gui.tools.locate import _dock_boxes

    frame = ViewFrame(100, 100, 100, 100, 50, 50, Path("/tmp/current.png"))
    boxes, status = _dock_boxes("Chrome", frame=frame, width=100, height=100)

    assert boxes == []
    assert status == "outside_current_frame"
