"""macOS AX 结构化 UI 后端协议与可记录的测试替身。

协议只为当前前台应用提供受限的 AX 观察与动作能力；网页未暴露的控件继续使用视觉
桌面后备。测试替身不访问系统辅助功能 API。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from max_gui.ui import UIElement


class MacOSAXBackend(Protocol):
    """macOS 原生 UI 的受限观察与 AX 动作契约。"""

    def observe(self) -> list[UIElement]:
        """返回前台窗口的有限 AX 元素；不可用时返回空列表。"""
        ...

    def press(self, element: UIElement) -> None:
        """执行已验证元素的 AXPress；失败时抛运行时异常。"""
        ...

    def set_value(self, element: UIElement, text: str) -> None:
        """为已验证可编辑元素设值；失败时抛运行时异常。"""
        ...

    def activate(self, app_id: str) -> None:
        """激活当前已观察到的原生应用；未找到或前台漂移时抛运行时异常。"""
        ...


@dataclass(slots=True)
class FakeMacOSAXBackend:
    """记录 AX 调用的测试后端，可注入元素与动作失败。"""

    elements: list[UIElement] = field(default_factory=list)
    calls: list[tuple[str, str]] = field(default_factory=list)
    fail: bool = False

    def observe(self) -> list[UIElement]:
        """返回预置元素副本。"""
        return list(self.elements)

    def press(self, element: UIElement) -> None:
        """记录 AXPress。"""
        self._record("press", element)

    def set_value(self, element: UIElement, text: str) -> None:
        """记录 AXValue 设置，不记录文本。"""
        self._record("set_value", element)

    def activate(self, app_id: str) -> None:
        """记录对已观察应用的激活，不保存应用展示名称。"""
        if self.fail:
            raise RuntimeError("macOS AX 后端动作失败")
        self.calls.append(("activate", app_id))

    def _record(self, action: str, element: UIElement) -> None:
        """追加调用记录，并按配置模拟 AX 错误。"""
        if self.fail:
            raise RuntimeError("macOS AX 后端动作失败")
        self.calls.append((action, element.id))
