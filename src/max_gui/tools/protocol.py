"""工具协议：确认范围、错误、多模态结果与 OpenAI function schema。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

ConfirmationScope = Literal["workspace", "desktop", "none"]


class ToolError(RuntimeError):
    """工具业务失败，注册表会把消息原样返回给模型。"""


class ConfirmationGate(Protocol):
    """执行前向用户确认；返回 `True` 才真正调用。"""

    async def confirm(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        scope: ConfirmationScope = "workspace",
    ) -> bool:
        """询问是否允许执行。

        参数：
            tool_name: 工具名。
            arguments: 已解析参数。
            scope: `workspace` / `desktop` / `none`。

        返回：
            是否放行。
        """
        ...


@dataclass(slots=True)
class ToolResult:
    """可回注图像的工具结果。

    字段：
        text: 给模型的文本摘要。
        images: 本地图像路径，推理层会编成 `image_url`。
        ok: 工具调用是否成功。
        code: 稳定的机器可读结果码。
        data: 可选的脱敏执行事实；不表示任务进度或业务完成。
    """

    text: str
    images: list[Path] = field(default_factory=list)
    ok: bool = True
    code: str = "ok"
    data: dict[str, Any] = field(default_factory=dict)

    def __contains__(self, value: object) -> bool:
        """兼容既有测试和调用方对文本结果使用 `in` 的判断。"""
        return isinstance(value, str) and value in self.text

    def __str__(self) -> str:
        """返回模型与 TUI 可读的中文摘要。"""
        return self.text


@dataclass(slots=True)
class Tool:
    """单个可调用工具及其 JSON Schema。

    字段：
        name / description / parameters: 暴露给模型的 function 定义。
        invoke: 异步实现，入参为参数字典。
        confirmation_scope: 非 `none` 时走确认门。
        side_effect: 是否改变真实桌面环境。
    """

    name: str
    description: str
    parameters: dict[str, Any]
    invoke: Callable[[dict[str, Any]], Awaitable[str | ToolResult]]
    confirmation_scope: ConfirmationScope = "none"
    side_effect: bool = False

    @property
    def requires_confirmation(self) -> bool:
        """是否需要在调用前经过确认门。"""
        return self.confirmation_scope != "none"

    def schema(self) -> dict[str, Any]:
        """生成递归拒绝未知对象字段的 OpenAI function schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": _strict_object_schemas(self.parameters),
            },
        }


def _strict_object_schemas(schema: dict[str, Any]) -> dict[str, Any]:
    """复制 JSON Schema，并让每层对象默认拒绝未声明属性。"""
    strict = deepcopy(schema)

    def visit(node: Any) -> None:
        """递归处理 properties 与 items 中的嵌套 schema。"""
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            node.setdefault("additionalProperties", False)
        for child in (node.get("properties") or {}).values():
            visit(child)
        visit(node.get("items"))

    visit(strict)
    return strict
