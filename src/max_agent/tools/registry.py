"""工具的唯一注册与调用入口，负责输入校验及统一失败回执。"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ValidationError

from max_agent.tools.base import Tool, ToolFailureCode, ToolReceipt


class ToolRegistry:
    """按稳定名称管理工具，阻止编排器绕过工具契约。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def invoke(self, name: str, payload: Mapping[str, object]) -> ToolReceipt:
        tool = self._tools.get(name)
        if tool is None:
            return ToolReceipt.failure(
                name, ToolFailureCode.UNKNOWN_TOOL, f"unknown tool: {name}"
            )
        try:
            tool_input = tool.input_model.model_validate(payload)
        except ValidationError as error:
            return ToolReceipt.failure(
                name, ToolFailureCode.INVALID_INPUT, str(error.errors()[0]["msg"])
            )
        try:
            return tool.invoke(tool_input)
        except (
            Exception
        ) as error:  # tool boundary: external runtime errors become receipts
            return ToolReceipt.failure(
                name,
                ToolFailureCode.EXECUTION_FAILED,
                f"{type(error).__name__}: {error}",
            )

    def read_only_tools(self) -> tuple[dict[str, object], ...]:
        descriptions = []
        for name, tool in self._tools.items():
            if not getattr(tool, "read_only", True):
                continue
            try:
                schema = tool.input_model.model_json_schema()
            except Exception:
                schema = {}
            descriptions.append(
                {
                    "name": name,
                    "description": getattr(tool, "description", name),
                    "input_schema": schema,
                }
            )
        return tuple(descriptions)


def build_default_registry() -> ToolRegistry:
    """组装当前已实现的感知工具；不注册尚未实现的能力。"""
    from max_agent.tools.perception.ocr import RecognizeTextTool
    from max_agent.tools.perception.screen import ObserveScreenTool
    from max_agent.tools.perception.som import AnnotateSomTool
    from max_agent.tools.perception.uia import ObserveUiElementsTool
    from max_agent.tools.perception.vision import MatchTemplateTool, PreprocessImageTool

    registry = ToolRegistry()
    for tool in (
        ObserveScreenTool(),
        RecognizeTextTool(),
        ObserveUiElementsTool(),
        PreprocessImageTool(),
        MatchTemplateTool(),
        AnnotateSomTool(),
    ):
        registry.register(tool)
    return registry
