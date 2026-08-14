"""LangGraph ReAct 状态：会话消息、待执行工具调用与回合状态。"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

AgentStatus = Literal["thinking", "acting", "observing", "done", "error", "interrupted"]


class AgentState(TypedDict, total=False):
    """单回合在图节点之间传递的可变状态。

    字段：
        session_id: 当前会话编号。
        messages: OpenAI 风格消息列表，content 多为 `{text, images}`。
        images: 本回合用户附带的图像路径。
        pending_tool_calls: Think 产出的调用，或 Act 写回的工具结果。
        iteration: 已完成的 Think-Act-Observe 圈数。
        status: 当前节点或终态。
        error: 失败时的人类可读说明。
    """

    session_id: str
    messages: list[dict[str, Any]]
    images: list[str]
    pending_tool_calls: list[dict[str, Any]]
    iteration: int
    status: AgentStatus
    error: str | None
