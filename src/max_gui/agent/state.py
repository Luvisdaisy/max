from __future__ import annotations

from typing import Any, Literal, TypedDict

AgentStatus = Literal["thinking", "acting", "observing", "done", "error", "interrupted"]


class AgentState(TypedDict, total=False):
    session_id: str
    messages: list[dict[str, Any]]
    images: list[str]
    pending_tool_calls: list[dict[str, Any]]
    iteration: int
    status: AgentStatus
    error: str | None
