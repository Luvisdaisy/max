from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from max_gui.agent.state import AgentState
from max_gui.config import Settings
from max_gui.inference.client import ChatDelta, InferenceClient, to_chat_messages
from max_gui.session.store import Session, SessionMessage, SessionStore
from max_gui.tools.desktop import current_session_id
from max_gui.tools.protocol import ToolResult
from max_gui.tools.registry import ToolRegistry

ITERATION_LIMIT_MESSAGE = "已达到最大迭代次数，本回合停止。"


class AgentRunner:
    def __init__(
        self,
        settings: Settings,
        client: InferenceClient,
        registry: ToolRegistry,
        store: SessionStore,
    ) -> None:
        self.settings = settings
        self.client = client
        self.registry = registry
        self.store = store
        self._interrupt = asyncio.Event()
        self._on_token: Callable[[str], None] | None = None
        self._graph = _build_graph(self)

    def interrupt(self) -> None:
        self._interrupt.set()

    def clear_interrupt(self) -> None:
        self._interrupt.clear()

    async def run(
        self,
        session: Session,
        *,
        user_text: str | None = None,
        image_paths: list[str] | None = None,
        resume: bool = False,
        on_token: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> AgentState:
        self.clear_interrupt()
        self._on_token = on_token
        token = current_session_id.set(session.id)
        try:
            if resume and session.checkpoint:
                state: AgentState = dict(session.checkpoint)  # type: ignore[assignment]
                state["session_id"] = session.id
            else:
                messages = [_message_to_state(item) for item in session.messages]
                if user_text is not None:
                    images = [{"path": path} for path in (image_paths or [])]
                    user_msg = {"role": "user", "content": {"text": user_text, "images": images}}
                    messages.append(user_msg)
                    self.store.append_messages(
                        session,
                        [SessionMessage(role="user", content=user_msg["content"])],
                    )
                state = {
                    "session_id": session.id,
                    "messages": messages,
                    "images": list(image_paths or []),
                    "pending_tool_calls": [],
                    "iteration": 0,
                    "status": "thinking",
                    "error": None,
                }

            if on_status:
                on_status(str(state.get("status") or "thinking"))

            result = await self._graph.ainvoke(state)
            self._persist(session, result)
            return result
        finally:
            current_session_id.reset(token)

    async def think(self, state: AgentState) -> AgentState:
        if self._interrupt.is_set():
            return {**state, "status": "interrupted"}
        if int(state.get("iteration") or 0) >= self.settings.max_iterations:
            messages = list(state.get("messages") or [])
            messages.append({"role": "assistant", "content": {"text": ITERATION_LIMIT_MESSAGE}})
            return {
                **state,
                "messages": messages,
                "status": "error",
                "error": ITERATION_LIMIT_MESSAGE,
                "pending_tool_calls": [],
            }

        encoded = to_chat_messages(list(state.get("messages") or []), settings=self.settings)
        delta: ChatDelta = await self.client.stream(
            encoded,
            tools=self.registry.schemas(),
            on_token=self._on_token,
            should_stop=self._interrupt.is_set,
        )
        if self._interrupt.is_set() or delta.finish_reason == "interrupted":
            messages = list(state.get("messages") or [])
            if delta.text:
                messages.append({"role": "assistant", "content": {"text": delta.text}})
            return {**state, "messages": messages, "status": "interrupted"}

        messages = list(state.get("messages") or [])
        assistant: dict[str, Any] = {"role": "assistant", "content": {"text": delta.text}}
        if delta.tool_calls:
            assistant["tool_calls"] = delta.tool_calls
            messages.append(assistant)
            return {
                **state,
                "messages": messages,
                "pending_tool_calls": delta.tool_calls,
                "status": "acting",
            }
        messages.append(assistant)
        return {**state, "messages": messages, "pending_tool_calls": [], "status": "done"}

    async def act(self, state: AgentState) -> AgentState:
        if self._interrupt.is_set():
            return {**state, "status": "interrupted"}
        results: list[dict[str, Any]] = []
        for call in state.get("pending_tool_calls") or []:
            if self._interrupt.is_set():
                return {**state, "status": "interrupted"}
            fn = call.get("function") or {}
            name = str(fn.get("name") or "")
            output = await self.registry.invoke(name, fn.get("arguments"))
            if isinstance(output, ToolResult):
                content: Any = {
                    "text": output.text,
                    "images": [{"path": str(path)} for path in output.images],
                }
            else:
                content = output
            results.append(
                {
                    "role": "tool",
                    "content": content,
                    "tool_call_id": call.get("id") or name,
                    "name": name,
                }
            )
        return {
            **state,
            "pending_tool_calls": results,
            "status": "observing",
        }

    async def observe(self, state: AgentState) -> AgentState:
        messages = list(state.get("messages") or [])
        tool_messages = list(state.get("pending_tool_calls") or [])
        messages.extend(tool_messages)
        return {
            **state,
            "messages": messages,
            "pending_tool_calls": [],
            "iteration": int(state.get("iteration") or 0) + 1,
            "status": "thinking",
        }

    def _persist(self, session: Session, state: AgentState) -> None:
        session.status = str(state.get("status") or "done")
        session.checkpoint = dict(state)
        known = len(session.messages)
        extras = list(state.get("messages") or [])[known:]
        if extras:
            self.store.append_messages(
                session, [_state_to_session_message(item) for item in extras]
            )
        else:
            self.store.save(session)


def _build_graph(runner: AgentRunner):
    graph = StateGraph(AgentState)
    graph.add_node("think", runner.think)
    graph.add_node("act", runner.act)
    graph.add_node("observe", runner.observe)
    graph.add_edge(START, "think")
    graph.add_conditional_edges("think", _route_after_think)
    graph.add_edge("act", "observe")
    graph.add_edge("observe", "think")
    return graph.compile()


def _route_after_think(state: AgentState) -> Literal["act", "__end__"]:
    if state.get("status") == "acting":
        return "act"
    return END


def _message_to_state(message: SessionMessage) -> dict[str, Any]:
    item: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.content.get("tool_calls"):
        item["tool_calls"] = message.content["tool_calls"]
    if message.content.get("tool_call_id"):
        item["tool_call_id"] = message.content["tool_call_id"]
    return item


def _state_to_session_message(item: dict[str, Any]) -> SessionMessage:
    content = item.get("content")
    if isinstance(content, str):
        payload: dict[str, Any] = {"text": content}
    elif isinstance(content, dict):
        payload = dict(content)
    else:
        payload = {"text": str(content or "")}
    if item.get("tool_calls"):
        payload["tool_calls"] = item["tool_calls"]
    if item.get("tool_call_id"):
        payload["tool_call_id"] = item["tool_call_id"]
    return SessionMessage(role=str(item.get("role") or "assistant"), content=payload)
