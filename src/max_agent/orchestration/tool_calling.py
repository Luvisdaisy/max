"""受限只读工具选择、执行与净化结果回传。"""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from max_agent.orchestration.models import summarize_data
from max_agent.tools.registry import ToolRegistry

# 固定摘要既让模型理解能力边界，也避免把校验细节、异常文本或工具回执带入最终提示。
_SAFE_FAILURE_SUMMARIES = {
    "invalid_tool_selection": "模型返回的工具选择格式无效。",
    "tool_not_allowed": "所选工具未获准用于当前只读会话。",
    "invalid_input": "工具输入不符合调用契约。",
    "unknown_tool": "所选工具未注册。",
    "unavailable": "工具当前不可用。",
    "execution_failed": "工具执行失败。",
    "tool_failed": "工具未能完成调用。",
}


class ToolSelectionError(RuntimeError):
    """表示模型已返回内容，但内容不能构成受支持的工具选择。"""


class ToolSelection(BaseModel):
    """模型工具选择的严格输入结构。"""

    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolExplanation(BaseModel):
    """最终解释及仅供业务层使用的压缩工具回执。"""

    text: str
    tool_name: str | None = None
    receipt: dict[str, Any]


class ReadOnlyToolExplainer:
    """最多运行一个注册的只读工具，再让模型解释内存观察。"""

    def __init__(
        self,
        registry: ToolRegistry,
        select: Callable[[str, tuple[dict[str, object], ...]], object],
        explain: Callable[[str, dict[str, Any]], str],
        on_tool_event: Callable[[str, str, float], None] | None = None,
    ) -> None:
        self._registry = registry
        self._select = select
        self._explain = explain
        # 回调签名不接收参数或回执，确保 UI 边界只能获得净化状态。
        self._on_tool_event = on_tool_event

    def _emit_tool_event(self, tool_name: str, state: str, started_at: float) -> None:
        """报告工具名、固定状态与单调时钟耗时，不泄漏业务数据。"""
        if self._on_tool_event is not None:
            self._on_tool_event(tool_name, state, perf_counter() - started_at)

    def _explain_failure(
        self, goal: str, code: str, tool_name: str | None = None
    ) -> ToolExplanation:
        """将失败压缩为白名单观察，并继续生成本轮最终回复。"""
        failure = {
            "code": code,
            "summary": _SAFE_FAILURE_SUMMARIES.get(
                code, _SAFE_FAILURE_SUMMARIES["tool_failed"]
            ),
        }
        # 只有注册表确认过的工具名才可进入观察，避免回显模型虚构的任意名称。
        if tool_name is not None:
            failure["tool_name"] = tool_name
        observation = {"tool_failure": failure}
        return ToolExplanation(
            text=self._explain(goal, observation),
            tool_name=tool_name,
            receipt=observation,
        )

    def run(self, goal: str) -> ToolExplanation:
        tools = self._registry.read_only_tools()
        try:
            selection = ToolSelection.model_validate(self._select(goal, tools))
        except (ToolSelectionError, ValidationError):
            return self._explain_failure(goal, "invalid_tool_selection")
        if selection.tool_name is None:
            return ToolExplanation(text=self._explain(goal, {}), receipt={})
        allowed_tools = {tool["name"] for tool in tools}
        if selection.tool_name not in allowed_tools:
            return self._explain_failure(goal, "tool_not_allowed")
        started_at = perf_counter()
        self._emit_tool_event(selection.tool_name, "running", started_at)
        receipt = self._registry.invoke(selection.tool_name, selection.arguments)
        if not receipt.success:
            self._emit_tool_event(selection.tool_name, "failed", started_at)
            code = str(receipt.error.code) if receipt.error else "tool_failed"
            return self._explain_failure(goal, code, selection.tool_name)
        observation = dict(receipt.data)
        self._emit_tool_event(selection.tool_name, "succeeded", started_at)
        return ToolExplanation(
            text=self._explain(goal, observation),
            tool_name=selection.tool_name,
            receipt=summarize_data(observation),
        )
