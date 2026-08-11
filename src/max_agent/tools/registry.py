"""工具唯一注册与调用入口，统一执行 schema、阶段、预算和超时校验。"""

from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from pydantic import ValidationError

from max_agent.tools.base import (
    Tool,
    ToolContext,
    ToolFailureCode,
    ToolPermission,
    ToolPhase,
    ToolReceipt,
)


class ToolRegistry:
    """按稳定名称管理工具，并区分模型可见能力与运行时内部能力。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def invoke(
        self,
        name: str,
        payload: Mapping[str, object],
        context: ToolContext | None = None,
    ) -> ToolReceipt:
        tool = self._tools.get(name)
        if tool is None:
            return ToolReceipt.failure(
                name, ToolFailureCode.UNKNOWN_TOOL, "unknown tool"
            )
        if context is not None:
            if context.cancellation.cancelled:
                return ToolReceipt.failure(
                    name, ToolFailureCode.CANCELLED, "task cancelled"
                )
            if context.phase not in tool.allowed_phases:
                return ToolReceipt.failure(
                    name,
                    ToolFailureCode.PHASE_DENIED,
                    "tool is unavailable in this phase",
                )
            permission = getattr(tool, "permission", ToolPermission.OBSERVE)
            bucket = (
                "model_turns"
                if permission == ToolPermission.MODEL
                else "actions"
                if permission == ToolPermission.CONTROL
                and context.phase == ToolPhase.ACTION
                else "tool_calls"
            )
            if not context.consume_budget(bucket):
                return ToolReceipt.failure(
                    name, ToolFailureCode.BUDGET_EXHAUSTED, "tool call budget exhausted"
                )
        unknown_fields = set(payload) - set(tool.input_model.model_fields)
        if (
            context is not None
            and unknown_fields
            and tool.input_model.model_config.get("extra") != "allow"
        ):
            return ToolReceipt.failure(
                name,
                ToolFailureCode.INVALID_INPUT,
                f"unknown input field: {sorted(unknown_fields)[0]}",
            )
        try:
            tool_input = tool.input_model.model_validate(payload)
        except ValidationError as error:
            return ToolReceipt.failure(
                name, ToolFailureCode.INVALID_INPUT, str(error.errors()[0]["msg"])
            )
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"max-{name}")
        future = (
            executor.submit(tool.invoke, tool_input, context)
            if context is not None
            else executor.submit(tool.invoke, tool_input)
        )
        try:
            return future.result(timeout=getattr(tool, "timeout_seconds", 30.0))
        except TimeoutError:
            future.cancel()
            return ToolReceipt.failure(
                name, ToolFailureCode.TIMEOUT, "tool call timed out"
            )
        except Exception as error:
            return ToolReceipt.failure(
                name,
                ToolFailureCode.EXECUTION_FAILED,
                f"tool execution failed: {type(error).__name__}",
            )
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def model_tools(
        self, phase: ToolPhase = ToolPhase.TOOL
    ) -> tuple[dict[str, object], ...]:
        """只向模型暴露当前阶段允许且显式标记的工具。"""
        descriptions: list[dict[str, object]] = []
        for name, tool in self._tools.items():
            if not getattr(tool, "model_visible", True) or phase not in getattr(
                tool, "allowed_phases", {phase}
            ):
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
                    "permission": getattr(tool, "permission", "observe"),
                    "side_effect": getattr(tool, "side_effect", False),
                }
            )
        return tuple(descriptions)

    def read_only_tools(self) -> tuple[dict[str, object], ...]:
        """兼容旧解释器，只返回模型可见且无副作用的工具。"""
        return tuple(item for item in self.model_tools() if not item["side_effect"])


def build_default_registry(**kwargs: object) -> ToolRegistry:
    """组装全部已实现工具；可选依赖由调用方显式注入。"""
    from max_agent.tools.perception.ocr import RecognizeTextTool
    from max_agent.tools.perception.screen import ObserveScreenTool
    from max_agent.tools.perception.som import AnnotateSomTool
    from max_agent.tools.perception.uia import ObserveUiElementsTool, ObserveWindowsTool
    from max_agent.tools.perception.vision import MatchTemplateTool, PreprocessImageTool

    registry = ToolRegistry()
    for tool in (
        ObserveScreenTool(),
        ObserveWindowsTool(),
        RecognizeTextTool(kwargs.get("ocr_model_dir")),
        ObserveUiElementsTool(),
        PreprocessImageTool(),
        MatchTemplateTool(),
        AnnotateSomTool(),
    ):
        registry.register(tool)
    return registry
