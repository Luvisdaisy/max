"""基于短期 UI 快照的语义操作工具。

模型只能提交元素编号与快照版本。本模块在进程内解析对应 locator，并分派到浏览器或
macOS AX 后端；不会接受坐标、selector、后端名称，也不会把输入正文写入动作结果。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from max_gui.desktop.backend import DesktopBackend
from max_gui.desktop.ui_backends import BrowserBackend, MacOSAXBackend
from max_gui.tools.protocol import Tool, ToolError, ToolResult
from max_gui.ui import StaleUIError, UIElement, UIRegistry


class SemanticResolver:
    """解析当前 UI 版本并以对应结构化后端执行受限动作。"""

    def __init__(
        self,
        registry: UIRegistry,
        *,
        browser: BrowserBackend | None,
        macos_ax: MacOSAXBackend | None,
        workspace: Path,
        desktop: DesktopBackend,
    ) -> None:
        """保存当前快照表、可选后端与文件输入允许的工作区根目录。"""
        self.registry = registry
        self.browser = browser
        self.macos_ax = macos_ax
        self.workspace = workspace.resolve()
        self.desktop = desktop

    def element(self, arguments: dict[str, Any]) -> UIElement:
        """按模型提交的短期编号和版本解析元素，过期时转成稳定工具错误。"""
        try:
            return self.registry.resolve(
                element_id=str(arguments["element_id"]), version=int(arguments["ui_version"])
            )
        except (KeyError, TypeError, ValueError, StaleUIError) as exc:
            raise ToolError(str(exc)) from exc

    async def click(self, arguments: dict[str, Any], *, double: bool = False) -> ToolResult:
        """以 browser locator 或 AXPress 执行点击，vision 元素要求保留坐标后备。"""
        element = self.element(arguments)
        if element.backend == "browser" and self.browser is not None:
            await self.browser.click(element, double=double)
        elif element.backend == "macos_ax" and self.macos_ax is not None and not double:
            self.macos_ax.press(element)
        elif element.backend == "vision":
            raise ToolError("视觉元素请使用当前截图上的既有坐标工具")
        else:
            raise ToolError("当前元素的结构化后端不可用，请重新观察")
        return ToolResult("结构化点击已分派，等待后置观察验证。")

    async def type_text(self, arguments: dict[str, Any]) -> ToolResult:
        """向当前可编辑 browser 或 AX 元素写入文本，不在返回值中回显正文。"""
        element = self.element(arguments)
        text = str(arguments["text"])
        if element.backend == "browser" and self.browser is not None:
            await self.browser.fill(element, text, clear_first=bool(arguments.get("clear_first")))
        elif element.backend == "macos_ax" and self.macos_ax is not None:
            self.macos_ax.set_value(element, text)
        else:
            raise ToolError("当前元素不支持结构化输入，请重新观察或使用视觉后备")
        return ToolResult("结构化输入已分派，等待后置观察验证。")

    async def select_option(self, arguments: dict[str, Any]) -> ToolResult:
        """为当前 browser select 设置选项，不记录选项正文。"""
        element = self.element(arguments)
        if element.backend != "browser" or self.browser is None:
            raise ToolError("当前元素不支持浏览器选项选择")
        await self.browser.select_option(element, str(arguments["value"]))
        return ToolResult("下拉选项已设置，等待后置观察验证。")

    async def set_file_input(self, arguments: dict[str, Any]) -> ToolResult:
        """为当前 file input 设置工作区内可访问的文件，拒绝越界与目录。"""
        element = self.element(arguments)
        raw_path = Path(str(arguments["file_path"])).expanduser().resolve()
        if not raw_path.is_file() or not raw_path.is_relative_to(self.workspace):
            raise ToolError("文件必须是工作区内可访问的普通文件")
        if element.backend != "browser" or self.browser is None:
            raise ToolError("当前元素不支持浏览器文件上传快路径")
        await self.browser.set_file_input(element, str(raw_path))
        return ToolResult("文件已通过浏览器快路径设置，等待后置观察验证。")

    async def scroll(self, arguments: dict[str, Any]) -> ToolResult:
        """在当前 browser 元素范围内滚动；AX 与 vision 保持既有后备边界。"""
        element = self.element(arguments)
        if element.backend != "browser" or self.browser is None:
            raise ToolError("当前元素不支持结构化滚动，请使用视觉后备")
        await self.browser.scroll(element, delta_y=int(arguments["delta_y"]))
        return ToolResult("页面已滚动，等待后置观察验证。")

    async def navigate(self, arguments: dict[str, Any]) -> ToolResult:
        """仅在存在有效 browser 快照时导航受控页面。"""
        current = self.registry.current
        if current is None or current.context != "browser" or self.browser is None:
            raise ToolError("当前没有可用的受控浏览器页面")
        await self.browser.navigate(str(arguments["url"]))
        return ToolResult("受控页面已开始导航，等待后置观察验证。")

    async def press_key(self, arguments: dict[str, Any]) -> ToolResult:
        """对当前前台按单个命名键；确认门和后置观察仍由工具层统一处理。"""
        await asyncio.to_thread(self.desktop.press, str(arguments["key"]))
        return ToolResult("按键已执行，等待后置观察验证。")

    async def press_shortcut(self, arguments: dict[str, Any]) -> ToolResult:
        """对当前前台按组合键，不向状态层记录具体按键正文。"""
        await asyncio.to_thread(self.desktop.hotkey, *(str(item) for item in arguments["keys"]))
        return ToolResult("快捷键已执行，等待后置观察验证。")

    async def drag(self, arguments: dict[str, Any]) -> ToolResult:
        """以同一浏览器快照的两个 locator 执行拖放，版本错误时拒绝分派。"""
        source = self.element(arguments)
        try:
            target = self.registry.resolve(
                element_id=str(arguments["target_element_id"]), version=int(arguments["ui_version"])
            )
        except (KeyError, TypeError, ValueError, StaleUIError) as exc:
            raise ToolError(str(exc)) from exc
        if source.backend != "browser" or target.backend != "browser" or self.browser is None:
            raise ToolError("当前仅支持浏览器元素间的结构化拖拽")
        await self.browser.drag_to(source, target)
        return ToolResult("浏览器拖拽已分派，等待后置观察验证。")

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
        return ToolResult("已请求激活当前观察到的应用，等待后置观察验证。")


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
            "点击当前 UI 快照中的元素。",
            target_properties(),
            lambda args: resolver.click(args),
            "desktop",
            True,
        ),
        Tool(
            "double_click",
            "双击当前浏览器 UI 元素。",
            target_properties(),
            lambda args: resolver.click(args, double=True),
            "desktop",
            True,
        ),
        Tool(
            "type_text",
            "向当前可编辑元素输入文本。",
            target_properties(
                {"text": {"type": "string", "minLength": 1}, "clear_first": {"type": "boolean"}}
            ),
            lambda args: resolver.type_text(args),
            "desktop",
            True,
        ),
        Tool(
            "select_option",
            "选择当前浏览器下拉框的选项。",
            target_properties({"value": {"type": "string", "minLength": 1}}),
            lambda args: resolver.select_option(args),
            "desktop",
            True,
        ),
        Tool(
            "set_file_input",
            "为当前浏览器文件输入设置工作区文件。",
            target_properties({"file_path": {"type": "string", "minLength": 1}}),
            lambda args: resolver.set_file_input(args),
            "desktop",
            True,
        ),
        Tool(
            "scroll",
            "在当前浏览器元素范围内滚动。",
            target_properties({"delta_y": {"type": "integer"}}),
            lambda args: resolver.scroll(args),
            "desktop",
            True,
        ),
        Tool(
            "open_url",
            "导航当前受控浏览器页面。",
            {
                "type": "object",
                "properties": {"url": {"type": "string", "minLength": 1}},
                "required": ["url"],
            },
            lambda args: resolver.navigate(args),
            "desktop",
            True,
        ),
        Tool(
            "drag",
            "拖拽当前 UI 快照中的元素到另一个元素。",
            target_properties({"target_element_id": {"type": "string", "minLength": 1}}),
            lambda args: resolver.drag(args),
            "desktop",
            True,
        ),
        Tool(
            "press_key",
            "向当前前台窗口按一个命名键。",
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
            "向当前前台窗口按组合键。",
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
            "激活当前观察到的原生应用。",
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
            "短暂等待界面更新后重新观察。",
            {"type": "object", "properties": {"milliseconds": {"type": "integer"}}, "required": []},
            wait_action,
        ),
    ]
