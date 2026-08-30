"""结构化 UI 后端协议与可记录的测试替身。

协议将浏览器、macOS AX 和视觉后备的执行能力收敛到统一 Resolver，真实 locator
仅由实现保存。测试替身不访问系统浏览器或辅助功能 API。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from max_gui.ui import UIElement


class BrowserBackend(Protocol):
    """受控浏览器的观察和 locator 动作契约。"""

    async def observe(self) -> tuple[str, list[UIElement]] | None:
        """返回当前 URL 与有限元素；不可用时返回空。"""
        ...

    async def click(self, element: UIElement, *, double: bool = False) -> None:
        """对当前 browser 元素执行 locator 点击；失败时抛运行时异常。"""
        ...

    async def fill(self, element: UIElement, text: str, *, clear_first: bool = False) -> None:
        """填充当前 browser 元素；实现不得记录输入正文。"""
        ...

    async def select_option(self, element: UIElement, value: str) -> None:
        """选择原生 select 项；元素不支持时抛运行时异常。"""
        ...

    async def set_file_input(self, element: UIElement, file_path: str) -> None:
        """为文件输入设置本地文件；路径策略由上层完成。"""
        ...

    async def scroll(self, element: UIElement, *, delta_y: int) -> None:
        """在元素所属页面滚动；失败时抛出稳定的运行时异常。"""
        ...

    async def navigate(self, url: str) -> None:
        """导航当前受控页面；实现必须保持在受控 Chrome 会话内。"""
        ...

    async def drag_to(self, source: UIElement, target: UIElement) -> None:
        """把当前 browser 源元素拖到当前 browser 目标元素；失败时抛异常。"""
        ...


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
class FakeBrowserBackend:
    """记录浏览器调用的测试后端，可注入观察结果和动作失败。"""

    observation: tuple[str, list[UIElement]] | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)
    fail: bool = False

    async def observe(self) -> tuple[str, list[UIElement]] | None:
        """返回预置观察，不产生真实浏览器访问。"""
        return self.observation

    async def click(self, element: UIElement, *, double: bool = False) -> None:
        """记录单击或双击；设为失败时抛异常。"""
        self._record("double_click" if double else "click", element)

    async def fill(self, element: UIElement, text: str, *, clear_first: bool = False) -> None:
        """仅记录填充动作名，绝不记录输入正文。"""
        self._record("clear_fill" if clear_first else "fill", element)

    async def select_option(self, element: UIElement, value: str) -> None:
        """记录选择动作，不记录选项正文。"""
        self._record("select_option", element)

    async def set_file_input(self, element: UIElement, file_path: str) -> None:
        """记录文件输入动作，不记录绝对路径。"""
        self._record("set_file_input", element)

    async def scroll(self, element: UIElement, *, delta_y: int) -> None:
        """记录滚动目标和动作名，不访问浏览器。"""
        self._record("scroll", element)

    async def navigate(self, url: str) -> None:
        """记录导航动作而不保存 URL 正文。"""
        if self.fail:
            raise RuntimeError("浏览器后端动作失败")
        self.calls.append(("navigate", "page"))

    async def drag_to(self, source: UIElement, target: UIElement) -> None:
        """记录浏览器拖放源元素，不保留目标私有 locator。"""
        self._record("drag", source)

    def _record(self, action: str, element: UIElement) -> None:
        """追加无敏感信息的调用记录，并按配置模拟失败。"""
        if self.fail:
            raise RuntimeError("浏览器后端动作失败")
        self.calls.append((action, element.id))


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
