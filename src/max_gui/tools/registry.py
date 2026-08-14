"""工具注册表：默认装配、确认门与按名调用。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max_gui.config import Settings
from max_gui.desktop.backend import DesktopBackend
from max_gui.desktop.pyautogui_backend import PyAutoGUIBackend
from max_gui.inference.ocr import OcrRuntime
from max_gui.tools.desktop import desktop_tools
from max_gui.tools.files import file_tools
from max_gui.tools.image import image_tool
from max_gui.tools.ocr import ocr_tools
from max_gui.tools.protocol import ConfirmationGate, ConfirmationScope, Tool, ToolError, ToolResult
from max_gui.tools.search import search_tool


class AutoApproveGate:
    """测试与无交互场景：一律放行。"""

    async def confirm(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        scope: ConfirmationScope = "workspace",
    ) -> bool:
        """忽略参数，始终返回 `True`。"""
        return True


class DenyGate:
    """测试用：一律拒绝，用于确认门路径。"""

    async def confirm(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        scope: ConfirmationScope = "workspace",
    ) -> bool:
        """忽略参数，始终返回 `False`。"""
        return False


class SessionScopedGate:
    """按会话开关分别控制工作区与桌面自动批准。"""

    def __init__(self, *, auto_approve: bool = False, auto_approve_desktop: bool = False) -> None:
        """参数：`auto_approve` 管工作区工具；`auto_approve_desktop` 管桌面点击/输入。"""
        self.auto_approve = auto_approve
        self.auto_approve_desktop = auto_approve_desktop

    async def confirm(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        scope: ConfirmationScope = "workspace",
    ) -> bool:
        """桌面范围看 `auto_approve_desktop`，工作区看 `auto_approve`。"""
        if scope == "desktop":
            return self.auto_approve_desktop
        if scope == "workspace":
            return self.auto_approve
        return True


class ToolRegistry:
    """按名查找、导出 schema，并在确认后调用。"""

    def __init__(self, tools: list[Tool], *, gate: ConfirmationGate | None = None) -> None:
        """参数：`tools` 列表；`gate` 缺省为 `AutoApproveGate`。"""
        self._tools = {tool.name: tool for tool in tools}
        self.gate = gate or AutoApproveGate()

    def get(self, name: str) -> Tool | None:
        """按名取工具；不存在返回 `None`。"""
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        """全部工具的 OpenAI function schema。"""
        return [tool.schema() for tool in self._tools.values()]

    async def invoke(self, name: str, arguments: dict[str, Any] | str | None) -> str | ToolResult:
        """解析参数、走确认门并调用。

        未知工具、拒绝确认或异常都返回错误字符串，不向外抛。
        """
        tool = self._tools.get(name)
        if tool is None:
            return f"工具错误：未知工具 {name}"
        parsed = _coerce_args(arguments)
        if tool.requires_confirmation:
            allowed = await self.gate.confirm(name, parsed, scope=tool.confirmation_scope)
            if not allowed:
                return "已取消：用户拒绝执行"
        try:
            return await tool.invoke(parsed)
        except ToolError as exc:
            return str(exc)
        except Exception as exc:
            return f"工具错误：{exc}"


def build_default_registry(
    settings: Settings,
    *,
    gate: ConfirmationGate | None = None,
    desktop: DesktopBackend | None = None,
    ocr: OcrRuntime | None = None,
) -> ToolRegistry:
    """装配文件、搜索、图像预处理、OCR 与桌面工具。

    参数：
        settings: 工作区、超时与截图目录。
        gate: 确认门；缺省自动批准。
        desktop: 桌面后端；缺省 `PyAutoGUIBackend`。
        ocr: OCR 运行时；缺省按配置懒启动。
    """
    backend = desktop or PyAutoGUIBackend()
    tools = [
        *file_tools(settings.workspace),
        search_tool(settings.workspace),
        image_tool(settings.workspace, settings),
        *ocr_tools(settings, ocr),
        *desktop_tools(settings, backend),
    ]
    return ToolRegistry(tools, gate=gate)


def _coerce_args(arguments: dict[str, Any] | str | None) -> dict[str, Any]:
    """把模型给出的参数收成字典。JSON 字符串会解析；解析失败放进 `raw`。"""
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    try:
        loaded = json.loads(arguments)
    except json.JSONDecodeError:
        return {"raw": arguments}
    return loaded if isinstance(loaded, dict) else {"raw": loaded}
