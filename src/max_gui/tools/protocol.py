from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

ConfirmationScope = Literal["workspace", "desktop", "none"]


class ToolError(RuntimeError):
    pass


class ConfirmationGate(Protocol):
    async def confirm(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        scope: ConfirmationScope = "workspace",
    ) -> bool: ...


@dataclass(slots=True)
class ToolResult:
    text: str
    images: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    invoke: Callable[[dict[str, Any]], Awaitable[str | ToolResult]]
    confirmation_scope: ConfirmationScope = "none"

    @property
    def requires_confirmation(self) -> bool:
        return self.confirmation_scope != "none"

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
