"""工具协议：确认范围、错误、多模态结果与 OpenAI function schema。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
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
    """

    text: str
    images: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class Tool:
    """单个可调用工具及其 JSON Schema。

    字段：
        name / description / parameters: 暴露给模型的 function 定义。
        invoke: 异步实现，入参为参数字典。
        confirmation_scope: 非 `none` 时走确认门。
    """

    name: str
    description: str
    parameters: dict[str, Any]
    invoke: Callable[[dict[str, Any]], Awaitable[str | ToolResult]]
    confirmation_scope: ConfirmationScope = "none"

    @property
    def requires_confirmation(self) -> bool:
        """是否需要在调用前经过确认门。"""
        return self.confirmation_scope != "none"

    def schema(self) -> dict[str, Any]:
        """OpenAI `tools` 数组中的一条 function 定义。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
