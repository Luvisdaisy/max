"""macOS 辅助功能 UI 后端。

只读取当前前台应用的有限可交互元素；执行前重新确认 pid 仍为前台。AX 引用只保留
在进程内 `UIElement.locator`，权限不足和平台不支持均安全降级为空观察。
"""

from __future__ import annotations

import platform
from typing import Any

from max_gui.desktop.observation import observe_desktop_identity
from max_gui.ui import UIElement


class MacOSAXUIBackend:
    """使用 AppKit／ApplicationServices 发现并操作前台原生控件。"""

    def observe(self) -> list[UIElement]:
        """读取活动窗口的直接子孙可交互元素；失败时返回空列表。"""
        modules = self._modules()
        if modules is None:
            return []
        appkit, ax = modules
        try:
            front = appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
            if front is None or not ax.AXIsProcessTrusted():
                return []
            pid = int(front.processIdentifier())
            root = ax.AXUIElementCreateApplication(pid)
            _, windows = ax.AXUIElementCopyAttributeValue(root, "AXWindows", None)
            if not windows:
                return []
            window = windows[0]
            _, number = ax.AXUIElementCopyAttributeValue(window, "AXWindowNumber", None)
            return self._walk(ax, window, pid, str(number or "") or None, depth=0)
        except Exception:
            return []

    def press(self, element: UIElement) -> None:
        """校验前台 pid 后调用 AXPress；不匹配时拒绝旧元素。"""
        ax, ref = self._validated_ref(element)
        error = ax.AXUIElementPerformAction(ref, "AXPress")
        if error != 0:
            raise RuntimeError("AXPress 执行失败")

    def set_value(self, element: UIElement, text: str) -> None:
        """校验元素可编辑后设置 AXValue；调用方不得持久化文本。"""
        if not element.editable:
            raise RuntimeError("目标不是可编辑原生元素")
        ax, ref = self._validated_ref(element)
        error = ax.AXUIElementSetAttributeValue(ref, "AXValue", text)
        if error != 0:
            raise RuntimeError("AXValue 设置失败")

    def activate(self, app_id: str) -> None:
        """按已观察的 PID 激活运行中应用，拒绝不存在的任意应用名称。"""
        modules = self._modules()
        if modules is None:
            raise RuntimeError("macOS AX 后端不可用")
        appkit, _ = modules
        try:
            app = appkit.NSRunningApplication.runningApplicationWithProcessIdentifier_(int(app_id))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("应用标识无效，请重新观察") from exc
        if app is None or not app.activateWithOptions_(0):
            raise RuntimeError("无法激活已观察应用")

    def _walk(
        self, ax: Any, node: Any, pid: int, window_id: str | None, *, depth: int
    ) -> list[UIElement]:
        """有限递归 AX 子树，返回常见交互角色并限制深度和数量。"""
        if depth > 4:
            return []
        _, children = ax.AXUIElementCopyAttributeValue(node, "AXChildren", None)
        result: list[UIElement] = []
        for child in children or []:
            _, role = ax.AXUIElementCopyAttributeValue(child, "AXRole", None)
            _, title = ax.AXUIElementCopyAttributeValue(child, "AXTitle", None)
            _, enabled = ax.AXUIElementCopyAttributeValue(child, "AXEnabled", None)
            _, focused = ax.AXUIElementCopyAttributeValue(child, "AXFocused", None)
            role_name = str(role or "unknown")
            mapped = {
                "AXButton": "button",
                "AXTextField": "textbox",
                "AXCheckBox": "checkbox",
                "AXMenuItem": "menuitem",
                "AXRow": "row",
            }.get(role_name, role_name)
            editable = role_name in {"AXTextField", "AXTextArea", "AXComboBox"}
            if role_name in {
                "AXButton",
                "AXTextField",
                "AXTextArea",
                "AXCheckBox",
                "AXMenuItem",
                "AXRow",
                "AXComboBox",
            }:
                result.append(
                    UIElement(
                        "",
                        mapped,
                        str(title or "").strip()[:120] or None,
                        None,
                        True,
                        bool(enabled is not False),
                        editable,
                        bool(focused),
                        str(pid),
                        window_id,
                        "macos_ax",
                        {"pid": pid, "window_id": window_id, "ref": child},
                    )
                )
            if len(result) < 80:
                result.extend(self._walk(ax, child, pid, window_id, depth=depth + 1))
            if len(result) >= 80:
                return result[:80]
        return result[:80]

    def _validated_ref(self, element: UIElement) -> tuple[Any, Any]:
        """确认元素来自当前前台 pid，返回 AX 模块与短期引用。"""
        modules = self._modules()
        if (
            modules is None
            or element.backend != "macos_ax"
            or not isinstance(element.locator, dict)
        ):
            raise RuntimeError("macOS AX 元素 locator 已失效")
        appkit, ax = modules
        front = appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if front is None or int(front.processIdentifier()) != int(element.locator.get("pid") or -1):
            raise RuntimeError("前台应用已变化，请先重新观察")
        current_window = (observe_desktop_identity().get("active_window") or {}).get("id")
        expected_window = element.locator.get("window_id")
        if expected_window and current_window and str(expected_window) != str(current_window):
            raise RuntimeError("前台窗口已变化，请先重新观察")
        ref = element.locator.get("ref")
        if ref is None:
            raise RuntimeError("macOS AX 元素 locator 已失效")
        return ax, ref

    @staticmethod
    def _modules() -> tuple[Any, Any] | None:
        """仅 macOS 且辅助功能模块可导入时返回依赖。"""
        if platform.system() != "Darwin":
            return None
        try:
            import AppKit
            import ApplicationServices
        except ImportError:
            return None
        return AppKit, ApplicationServices
