"""工具注册表：默认装配、确认门与按名调用。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any

from max_gui.config import Settings
from max_gui.desktop.backend import DesktopBackend
from max_gui.desktop.macos_ax import MacOSAXUIBackend
from max_gui.desktop.pyautogui_backend import PyAutoGUIBackend
from max_gui.desktop.ui_backends import MacOSAXBackend
from max_gui.inference.ocr import OcrRuntime
from max_gui.inference.omniparser import LocateRuntime
from max_gui.tools.desktop import desktop_tools
from max_gui.tools.image import image_tool
from max_gui.tools.locate import locate_tool
from max_gui.tools.ocr import ocr_tools
from max_gui.tools.protocol import ConfirmationGate, ConfirmationScope, Tool, ToolError, ToolResult
from max_gui.tools.semantic import SemanticResolver, semantic_tools
from max_gui.ui import UIRegistry


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

    def __init__(
        self,
        tools: list[Tool],
        *,
        gate: ConfirmationGate | None = None,
        timeout: float = 30.0,
        ui_registry: UIRegistry | None = None,
        macos_ax: MacOSAXBackend | None = None,
    ) -> None:
        """参数：`tools` 列表；`gate` 缺省自动批准；`timeout` 限制单次实现调用。"""
        self._tools = {tool.name: tool for tool in tools}
        self.gate = gate or AutoApproveGate()
        self.timeout = float(timeout)
        self.ui_registry = ui_registry or UIRegistry()
        self.macos_ax = macos_ax

    def get(self, name: str) -> Tool | None:
        """按名取工具；不存在返回 `None`。"""
        return self._tools.get(name)

    def schemas(self, names: set[str] | None = None) -> list[dict[str, Any]]:
        """按注册顺序导出允许名称的 OpenAI function schema；缺省导出全部。"""
        return [
            tool.schema() for tool in self._tools.values() if names is None or tool.name in names
        ]

    def names(self) -> set[str]:
        """返回全部已注册工具名的副本。"""
        return set(self._tools)

    def is_side_effect(self, name: str) -> bool:
        """未知工具按非副作用返回，分发前仍须单独拒绝未知名称。"""
        tool = self._tools.get(name)
        return bool(tool and tool.side_effect)

    async def invoke(self, name: str, arguments: dict[str, Any] | str | None) -> str | ToolResult:
        """解析参数、走确认门并调用。

        未知工具、参数错误、拒绝、超时或异常都返回结构化错误，不向外抛。
        """
        tool = self._tools.get(name)
        if tool is None:
            return _failure("unknown_tool", f"工具错误：未知工具 {name}")
        parsed, parse_error = _coerce_args(arguments)
        if parse_error:
            return _failure("invalid_arguments", parse_error)
        validation_error = _validate_json_value(parsed, tool.schema()["function"]["parameters"])
        if validation_error:
            return _failure("invalid_arguments", f"工具参数错误：{validation_error}")
        if tool.requires_confirmation:
            allowed = await self.gate.confirm(name, parsed, scope=tool.confirmation_scope)
            if not allowed:
                return _failure("cancelled", "已取消：用户拒绝执行")
        try:
            return await asyncio.wait_for(tool.invoke(parsed), timeout=self.timeout)
        except TimeoutError:
            return _failure("timeout", f"工具超时：{name} 超过 {self.timeout:g} 秒")
        except ToolError as exc:
            return _failure("tool_error", str(exc))
        except Exception as exc:
            return _failure("internal_error", f"工具错误：{exc}")


def build_default_registry(
    settings: Settings,
    *,
    gate: ConfirmationGate | None = None,
    desktop: DesktopBackend | None = None,
    ocr: OcrRuntime | None = None,
    locate: LocateRuntime | None = None,
    macos_ax: MacOSAXBackend | None = None,
) -> ToolRegistry:
    """装配图像预处理、OCR、界面定位与桌面工具。

    参数：
        settings: 工作区、超时与截图目录。
        gate: 确认门；缺省自动批准。
        desktop: 桌面后端；缺省 `PyAutoGUIBackend`。
        ocr: OCR 运行时；缺省按配置懒启动。
        locate: 可选的 OmniParser 运行时；仅显式注入时注册定位器，默认 Agent 不暴露该工具。
        macos_ax: 可选的当前前台应用 AX 后端；未注入时使用系统实现。
    """
    backend = desktop or PyAutoGUIBackend()
    ui_registry = UIRegistry()
    ax_backend = macos_ax or MacOSAXUIBackend()
    tools = [
        image_tool(settings.workspace, settings),
        *ocr_tools(settings, ocr),
        *desktop_tools(settings, backend),
        _task_complete_tool(),
        *semantic_tools(
            SemanticResolver(
                ui_registry,
                macos_ax=ax_backend,
                desktop=backend,
            )
        ),
    ]
    if locate is not None:
        # 默认 Agent 不暴露定位器；显式注入仅供离线调试与兼容测试。
        tools.insert(2, locate_tool(settings, locate))
    return ToolRegistry(
        tools,
        gate=gate,
        timeout=settings.tool_timeout,
        ui_registry=ui_registry,
        macos_ax=ax_backend,
    )


def _task_complete_tool() -> Tool:
    """构造由 Agent 二次校验状态的机器可识别完成声明工具。"""

    async def complete(args: dict[str, Any]) -> ToolResult:
        """接收已通过 schema 的摘要和可见证据，不在此判断 GUI 业务语义。"""
        return ToolResult(text="已收到任务完成声明，等待 Agent 核验后置截图。")

    return Tool(
        name="task_complete",
        description=(
            "仅在完成桌面副作用且已查看后置截图后调用。"
            "summary 简述结果，evidence 说明截图中可见的完成证据。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "minLength": 1},
                "evidence": {"type": "string", "minLength": 1},
            },
            "required": ["summary", "evidence"],
        },
        invoke=complete,
    )


def _failure(code: str, text: str) -> ToolResult:
    """构造不带图片的稳定结构化工具错误。"""
    return ToolResult(text=text, ok=False, code=code)


def _coerce_args(arguments: dict[str, Any] | str | None) -> tuple[dict[str, Any], str | None]:
    """把模型参数解析为对象，并单独返回不会泄露原文的错误。"""
    if arguments is None:
        return {}, None
    if isinstance(arguments, dict):
        return arguments, None
    if not isinstance(arguments, str):
        return {}, "参数必须是 JSON 对象"
    try:
        loaded = json.loads(arguments)
    except json.JSONDecodeError:
        return {}, "参数不是合法 JSON 对象"
    if not isinstance(loaded, dict):
        return {}, "参数必须是 JSON 对象"
    return loaded, None


def _validate_json_value(value: Any, schema: dict[str, Any], path: str = "参数") -> str | None:
    """校验项目工具使用的 JSON Schema 子集，返回第一条中文错误。"""
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            return f"{path}必须是对象"
        properties = schema.get("properties") or {}
        missing = [name for name in schema.get("required") or [] if name not in value]
        if missing:
            return f"{path}缺少必填字段：{', '.join(missing)}"
        if schema.get("additionalProperties") is False:
            extras = [str(name) for name in value if name not in properties]
            if extras:
                return f"{path}包含未知字段：{', '.join(extras)}"
        for name, item in value.items():
            child = properties.get(name)
            if isinstance(child, dict):
                error = _validate_json_value(item, child, f"{path}.{name}")
                if error:
                    return error
    elif expected == "array":
        if not isinstance(value, list):
            return f"{path}必须是数组"
        if len(value) < int(schema.get("minItems") or 0):
            return f"{path}至少需要 {schema['minItems']} 项"
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                error = _validate_json_value(item, item_schema, f"{path}[{index}]")
                if error:
                    return error
    elif expected == "string":
        if not isinstance(value, str):
            return f"{path}必须是字符串"
        if len(value) < int(schema.get("minLength") or 0):
            return f"{path}不能为空"
    elif expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return f"{path}必须是整数"
    elif expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"{path}必须是数字"
    elif expected == "boolean" and not isinstance(value, bool):
        return f"{path}必须是布尔值"
    if "enum" in schema and value not in schema["enum"]:
        return f"{path}不在允许值中"
    return None
