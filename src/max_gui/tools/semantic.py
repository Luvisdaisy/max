"""基于短期 UI 快照的语义操作工具。

模型只能提交元素编号与快照版本。本模块在进程内解析对应 AX 元素，并分派到 macOS
AX 后端；不会接受坐标、selector、后端名称，也不会把输入正文写入动作结果。
"""

from __future__ import annotations

import asyncio
from typing import Any

from max_gui.desktop.backend import DesktopBackend
from max_gui.desktop.ui_backends import MacOSAXBackend
from max_gui.tools.protocol import Tool, ToolError, ToolResult
from max_gui.ui import StaleUIError, UIElement, UIRegistry


class SemanticResolver:
    """解析当前 UI 版本并以对应结构化后端执行受限动作。"""

    def __init__(
        self,
        registry: UIRegistry,
        *,
        macos_ax: MacOSAXBackend | None,
        desktop: DesktopBackend,
    ) -> None:
        """保存当前快照表、可选 AX 后端与桌面按键后端。"""
        self.registry = registry
        self.macos_ax = macos_ax
        self.desktop = desktop

    def element(self, arguments: dict[str, Any]) -> UIElement:
        """按模型提交的短期编号和版本解析元素，过期时转成稳定工具错误。"""
        try:
            return self.registry.resolve(
                element_id=str(arguments["element_id"]), version=int(arguments["ui_version"])
            )
        except (KeyError, TypeError, ValueError, StaleUIError) as exc:
            raise ToolError(str(exc)) from exc

    @staticmethod
    def _result(action: str, element: UIElement | None = None) -> ToolResult:
        """构造不含 locator、坐标和输入正文的统一语义执行结果。"""
        data: dict[str, Any] = {"action": action}
        if element is not None:
            data["element_id"] = element.id
            data["backend"] = element.backend
        return ToolResult("语义动作已分派，等待后置观察验证。", data=data)

    async def click(self, arguments: dict[str, Any], *, double: bool = False) -> ToolResult:
        """以 AXPress 执行点击；视觉元素必须保留既有坐标后备。"""
        element = self.element(arguments)
        if element.backend == "macos_ax" and self.macos_ax is not None and not double:
            self.macos_ax.press(element)
        elif element.backend == "vision":
            raise ToolError("视觉元素请使用当前截图上的既有坐标工具")
        else:
            raise ToolError("当前元素的结构化后端不可用，请重新观察")
        return self._result("double_click" if double else "click", element)

    async def type_text(self, arguments: dict[str, Any]) -> ToolResult:
        """向当前可编辑 AX 元素写入文本，不在返回值中回显正文。"""
        element = self.element(arguments)
        text = str(arguments["text"])
        if element.backend == "macos_ax" and self.macos_ax is not None:
            self.macos_ax.set_value(element, text)
        else:
            raise ToolError("当前元素不支持结构化输入，请重新观察或使用视觉后备")
        return self._result("type_text", element)

    async def press_key(self, arguments: dict[str, Any]) -> ToolResult:
        """对当前前台按单个命名键；确认门和后置观察仍由工具层统一处理。"""
        await asyncio.to_thread(self.desktop.press, str(arguments["key"]))
        return ToolResult("按键已执行，等待后置观察验证。", data={"action": "press_key"})

    async def press_shortcut(self, arguments: dict[str, Any]) -> ToolResult:
        """对当前前台按组合键，不向状态层记录具体按键正文。"""
        await asyncio.to_thread(self.desktop.hotkey, *(str(item) for item in arguments["keys"]))
        return ToolResult("快捷键已执行，等待后置观察验证。", data={"action": "press_shortcut"})

    async def activate_app(self, arguments: dict[str, Any]) -> ToolResult:
        """仅激活当前 native 快照内出现过的应用 PID，拒绝任意应用启动请求。"""
        app_id = str(arguments["app_id"])
        current = self.registry.current
        if (
            current is None
            or current.context != "native"
            or self.macos_ax is None
            or app_id not in {item.app_id for item in current.elements if item.app_id}
        ):
            raise ToolError("应用不在当前原生 UI 快照中，请重新观察")
        self.macos_ax.activate(app_id)
        return ToolResult(
            "已请求激活当前观察到的应用，等待后置观察验证。", data={"action": "activate_app"}
        )


def semantic_tools(resolver: SemanticResolver) -> list[Tool]:
    """构造不暴露 locator 或坐标的语义工具集合。"""

    def target_properties(extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """生成所有目标型动作共享的严格短期元素引用 schema。"""
        return {
            "type": "object",
            "properties": {
                "element_id": {"type": "string", "minLength": 1},
                "ui_version": {"type": "integer"},
                **(extra or {}),
            },
            "required": ["element_id", "ui_version"],
        }

    async def wait_action(arguments: dict[str, Any]) -> ToolResult:
        """等待短时间供 UI 稳定；上限防止模型发起长阻塞。"""
        await asyncio.sleep(min(5, max(0, int(arguments.get("milliseconds") or 0))) / 1000)
        return ToolResult("等待结束，请重新观察界面。")

    return [
        Tool(
            "click",
            "点击当前 UI 快照中可见的元素。仅使用 VISIBLE UI 提供的 element_id；不得用于输入文本。",
            target_properties(),
            lambda args: resolver.click(args),
            "desktop",
            True,
        ),
        Tool(
            "type_text",
            "向当前 UI 快照中可编辑的元素输入文本；不得用于按钮或只读元素。",
            target_properties(
                {"text": {"type": "string", "minLength": 1}, "clear_first": {"type": "boolean"}}
            ),
            lambda args: resolver.type_text(args),
            "desktop",
            True,
        ),
        Tool(
            "press_key",
            "向当前前台窗口按一个命名键；仅在当前状态已确认输入目标时使用。",
            {
                "type": "object",
                "properties": {"key": {"type": "string", "minLength": 1}},
                "required": ["key"],
            },
            lambda args: resolver.press_key(args),
            "desktop",
            True,
        ),
        Tool(
            "press_shortcut",
            "向当前前台窗口按组合键；仅在当前状态已确认输入目标时使用。",
            {
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                    }
                },
                "required": ["keys"],
            },
            lambda args: resolver.press_shortcut(args),
            "desktop",
            True,
        ),
        Tool(
            "activate_app",
            "激活当前 native UI 快照中观察到的应用；不得用于启动未知应用。",
            {
                "type": "object",
                "properties": {"app_id": {"type": "string", "minLength": 1}},
                "required": ["app_id"],
            },
            lambda args: resolver.activate_app(args),
            "desktop",
            True,
        ),
        Tool(
            "wait",
            "短暂等待界面更新；等待结束后必须重新观察，不得据此假定任务完成。",
            {"type": "object", "properties": {"milliseconds": {"type": "integer"}}, "required": []},
            wait_action,
        ),
    ]
