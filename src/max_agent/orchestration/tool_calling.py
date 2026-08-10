from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from max_agent.orchestration.models import summarize_data
from max_agent.tools.registry import ToolRegistry


class ToolSelection(BaseModel):
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolExplanation(BaseModel):
    text: str
    tool_name: str | None = None
    receipt: dict[str, Any]


class ReadOnlyToolExplainer:
    def __init__(
        self,
        registry: ToolRegistry,
        select: Callable[[str, tuple[dict[str, object], ...]], object],
        explain: Callable[[str, dict[str, Any]], str],
    ) -> None:
        self._registry = registry
        self._select = select
        self._explain = explain

    def run(self, goal: str) -> ToolExplanation:
        tools = self._registry.read_only_tools()
        try:
            selection = ToolSelection.model_validate(self._select(goal, tools))
        except ValidationError as error:
            raise RuntimeError(
                f"invalid_tool_selection:{error.errors()[0]['msg']}"
            ) from None
        if selection.tool_name is None:
            return ToolExplanation(text=self._explain(goal, {}), receipt={})
        if selection.tool_name not in {tool["name"] for tool in tools}:
            raise RuntimeError(f"tool_not_allowed:{selection.tool_name}")
        receipt = self._registry.invoke(selection.tool_name, selection.arguments)
        if not receipt.success:
            code = receipt.error.code if receipt.error else "tool_failed"
            raise RuntimeError(f"tool_failed:{code}")
        observation = dict(receipt.data)
        return ToolExplanation(
            text=self._explain(goal, observation),
            tool_name=selection.tool_name,
            receipt=summarize_data(observation),
        )
