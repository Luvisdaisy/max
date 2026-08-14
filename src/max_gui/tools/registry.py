from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from max_gui.config import Settings
from max_gui.desktop.backend import DesktopBackend
from max_gui.desktop.pyautogui_backend import PyAutoGUIBackend
from max_gui.tools.desktop import desktop_tools
from max_gui.tools.files import file_tools
from max_gui.tools.image import image_tool
from max_gui.tools.protocol import ConfirmationGate, ConfirmationScope, Tool, ToolError, ToolResult
from max_gui.tools.python import python_tool
from max_gui.tools.search import search_tool


class AutoApproveGate:
    async def confirm(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        scope: ConfirmationScope = "workspace",
    ) -> bool:
        return True


class DenyGate:
    async def confirm(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        scope: ConfirmationScope = "workspace",
    ) -> bool:
        return False


class SessionScopedGate:
    def __init__(self, *, auto_approve: bool = False, auto_approve_desktop: bool = False) -> None:
        self.auto_approve = auto_approve
        self.auto_approve_desktop = auto_approve_desktop

    async def confirm(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        scope: ConfirmationScope = "workspace",
    ) -> bool:
        if scope == "desktop":
            return self.auto_approve_desktop
        if scope == "workspace":
            return self.auto_approve
        return True


class ToolRegistry:
    def __init__(self, tools: list[Tool], *, gate: ConfirmationGate | None = None) -> None:
        self._tools = {tool.name: tool for tool in tools}
        self.gate = gate or AutoApproveGate()

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values()]

    async def invoke(self, name: str, arguments: dict[str, Any] | str | None) -> str | ToolResult:
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
) -> ToolRegistry:
    backend = desktop or PyAutoGUIBackend()
    tools = [
        *file_tools(settings.workspace),
        search_tool(settings.workspace),
        python_tool(settings.workspace, settings.tool_timeout),
        image_tool(settings.workspace, settings),
        *desktop_tools(settings, backend),
    ]
    return ToolRegistry(tools, gate=gate)


def _coerce_args(arguments: dict[str, Any] | str | None) -> dict[str, Any]:
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return arguments
    try:
        loaded = json.loads(arguments)
    except json.JSONDecodeError:
        return {"raw": arguments}
    return loaded if isinstance(loaded, dict) else {"raw": loaded}
