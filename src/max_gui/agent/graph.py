"""LangGraph ReAct：Think 调模型，Act 调工具，Observe 把结果写回消息。"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from max_gui.agent.plan import advance_subtask_after_tools, ingest_assistant_plan
from max_gui.agent.prompts import compose_gui_system_prompt
from max_gui.agent.state import AgentState
from max_gui.config import Settings
from max_gui.inference.client import ChatDelta, InferenceClient, to_chat_messages
from max_gui.session.store import Session, SessionMessage, SessionStore
from max_gui.tools.desktop import (
    active_view_frame,
    current_session_id,
    restore_desktop_context,
    snapshot_desktop_context,
)
from max_gui.tools.protocol import ToolResult
from max_gui.tools.registry import ToolRegistry

ITERATION_LIMIT_MESSAGE = "已达到最大迭代次数，本回合停止。"


class AgentRunner:
    """驱动一轮或多轮 Think / Act / Observe，并把状态写入会话。"""

    def __init__(
        self,
        settings: Settings,
        client: InferenceClient,
        registry: ToolRegistry,
        store: SessionStore,
    ) -> None:
        """注入配置、推理客户端、工具表与会话存储。"""
        self.settings = settings
        self.client = client
        self.registry = registry
        self.store = store
        self._interrupt = asyncio.Event()
        self._on_token: Callable[[str], None] | None = None
        self._on_reasoning: Callable[[str], None] | None = None
        self._on_status: Callable[[str], None] | None = None
        self._on_message: Callable[[str, dict[str, Any]], None] | None = None
        self._session: Session | None = None
        self._graph = _build_graph(self)

    def interrupt(self) -> None:
        """请求中断当前 Think/Act；节点在检查点退出。"""
        self._interrupt.set()

    def clear_interrupt(self) -> None:
        """新回合开始前清除中断标志。"""
        self._interrupt.clear()

    async def run(
        self,
        session: Session,
        *,
        user_text: str | None = None,
        image_paths: list[str] | None = None,
        resume: bool = False,
        on_token: Callable[[str], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_message: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> AgentState:
        """跑完一图并持久化。

        开始时从会话恢复截图坐标系与定位表；结束或工具执行后写回。
        `think` / `act` 每提交一条消息就写入会话，不等整图结束。

        参数：
            session: 当前会话。
            user_text: 新用户输入；`resume` 时可为空。
            image_paths: 本回合附件。
            resume: 为真且存在 checkpoint 时从中断处继续。
            on_token: 流式正文回调。
            on_reasoning: 流式思考回调。
            on_status: 节点状态变化回调。
            on_message: 一条助手或工具消息已提交时回调。

        返回：
            终态 `AgentState`。
        """
        self.clear_interrupt()
        self._on_token = on_token
        self._on_reasoning = on_reasoning
        self._on_status = on_status
        self._on_message = on_message
        token = current_session_id.set(session.id)
        self._session = session
        restore_desktop_context(session.view_frame, session.locate_hits)
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
                    "plan": [],
                    "current_subtask": None,
                }

            if on_status:
                on_status(str(state.get("status") or "thinking"))

            result = await self._graph.ainvoke(state)
            self._persist(session, result)
            return result
        finally:
            self._flush_desktop_context()
            self._session = None
            current_session_id.reset(token)

    async def think(self, state: AgentState) -> AgentState:
        """调用模型。有工具调用则进入 `acting`，否则 `done`；超迭代或推理失败为 `error`。

        拼装完成后立即写入会话并回调 `on_message`。推理异常不抛出图外。
        """
        if self._interrupt.is_set():
            return {**state, "status": "interrupted"}
        self._emit_status("thinking")
        if int(state.get("iteration") or 0) >= self.settings.max_iterations:
            messages = list(state.get("messages") or [])
            assistant = {"role": "assistant", "content": {"text": ITERATION_LIMIT_MESSAGE}}
            messages.append(assistant)
            self._commit_message(assistant)
            return {
                **state,
                "messages": messages,
                "status": "error",
                "error": ITERATION_LIMIT_MESSAGE,
                "pending_tool_calls": [],
            }

        try:
            encoded = to_chat_messages(
                list(state.get("messages") or []),
                settings=self.settings,
                system=compose_gui_system_prompt(frame=active_view_frame()),
            )
            delta: ChatDelta = await self.client.stream(
                encoded,
                tools=self.registry.schemas(),
                on_token=self._on_token,
                on_reasoning=self._on_reasoning,
                should_stop=self._interrupt.is_set,
            )
        except Exception as exc:
            return {
                **state,
                "status": "error",
                "error": str(exc),
                "pending_tool_calls": [],
            }
        if self._interrupt.is_set() or delta.finish_reason == "interrupted":
            messages = list(state.get("messages") or [])
            if delta.text or delta.reasoning:
                assistant = {"role": "assistant", "content": _assistant_content(delta)}
                messages.append(assistant)
                self._commit_message(assistant)
            return {**state, "messages": messages, "status": "interrupted"}

        messages = list(state.get("messages") or [])
        assistant = {"role": "assistant", "content": _assistant_content(delta)}
        plan, current = ingest_assistant_plan(
            delta.text,
            list(state.get("plan") or []),
            state.get("current_subtask"),
        )
        if delta.tool_calls:
            assistant["tool_calls"] = delta.tool_calls
            messages.append(assistant)
            self._commit_message(assistant)
            return {
                **state,
                "messages": messages,
                "pending_tool_calls": delta.tool_calls,
                "status": "acting",
                "plan": plan,
                "current_subtask": current,
            }
        messages.append(assistant)
        self._commit_message(assistant)
        return {
            **state,
            "messages": messages,
            "pending_tool_calls": [],
            "status": "done",
            "plan": plan,
            "current_subtask": current,
        }

    async def act(self, state: AgentState) -> AgentState:
        """依次执行 `pending_tool_calls`，每完成一个即落盘并回调 `on_message`。"""
        if self._interrupt.is_set():
            return {**state, "status": "interrupted"}
        self._emit_status("acting")
        results: list[dict[str, Any]] = []
        for call in state.get("pending_tool_calls") or []:
            if self._interrupt.is_set():
                return {**state, "status": "interrupted"}
            fn = call.get("function") or {}
            name = str(fn.get("name") or "")
            started = time.perf_counter()
            output = await self.registry.invoke(name, fn.get("arguments"))
            duration_ms = int((time.perf_counter() - started) * 1000)
            has_image = False
            error: str | None = None
            if isinstance(output, ToolResult):
                text = output.text
                images = [{"path": str(path)} for path in output.images]
                has_image = bool(output.images)
            else:
                text = str(output)
                images = []
                if _tool_output_failed(output):
                    error = str(output)
            content: dict[str, Any] = {
                "text": text,
                "images": images,
                "name": name,
                "exec": {
                    "iteration": int(state.get("iteration") or 0),
                    "subtask": state.get("current_subtask"),
                    "arguments": _short_args(fn.get("arguments")),
                    "duration_ms": duration_ms,
                    "error": error,
                    "has_image": has_image,
                },
            }
            item = {
                "role": "tool",
                "content": content,
                "tool_call_id": call.get("id") or name,
                "name": name,
            }
            results.append(item)
            self._commit_message(item)
        self._flush_desktop_context()
        return {
            **state,
            "pending_tool_calls": results,
            "status": "observing",
        }

    async def observe(self, state: AgentState) -> AgentState:
        """把工具结果追加到消息，迭代计数加一，回到 `thinking`。"""
        self._emit_status("observing")
        messages = list(state.get("messages") or [])
        tool_messages = list(state.get("pending_tool_calls") or [])
        failed = any(_tool_message_failed(item) for item in tool_messages)
        plan, current = advance_subtask_after_tools(
            plan=list(state.get("plan") or []),
            current_subtask=state.get("current_subtask"),
            assistant_text=_last_assistant_text(messages),
            tool_failed=failed,
        )
        messages.extend(tool_messages)
        return {
            **state,
            "messages": messages,
            "pending_tool_calls": [],
            "iteration": int(state.get("iteration") or 0) + 1,
            "status": "thinking",
            "plan": plan,
            "current_subtask": current,
        }

    def _flush_desktop_context(self) -> None:
        """把当前视图坐标系与定位表写入会话并落盘。"""
        session = self._session
        if session is None:
            return
        frame, hits = snapshot_desktop_context()
        if frame is not None:
            session.view_frame = frame
        if hits:
            session.locate_hits = hits
        self.store.save(session)

    def _emit_status(self, status: str) -> None:
        """通知调用方当前节点状态。"""
        if self._on_status:
            self._on_status(status)

    def _commit_message(self, item: dict[str, Any]) -> None:
        """把一条图消息写入会话并通知 TUI；已在会话中则只回调。"""
        session_msg = _state_to_session_message(item)
        session = self._session
        if session is not None:
            self.store.append_messages(session, [session_msg])
        if self._on_message:
            self._on_message(session_msg.role, session_msg.content)

    def _persist(self, session: Session, state: AgentState) -> None:
        """写回 status、checkpoint、桌面坐标系；尚未落盘的消息才追加。"""
        session.status = str(state.get("status") or "done")
        session.checkpoint = dict(state)
        frame, hits = snapshot_desktop_context()
        if frame is not None:
            session.view_frame = frame
        if hits:
            session.locate_hits = hits
        known = len(session.messages)
        extras = list(state.get("messages") or [])[known:]
        if extras:
            self.store.append_messages(
                session, [_state_to_session_message(item) for item in extras]
            )
        else:
            self.store.save(session)


def _assistant_content(delta: ChatDelta) -> dict[str, Any]:
    """从流式回复收成助手 content；有思考才写 `reasoning`。"""
    payload: dict[str, Any] = {"text": delta.text}
    if delta.reasoning:
        payload["reasoning"] = delta.reasoning
    return payload


def _build_graph(runner: AgentRunner):
    """编译 START → think ⇄ act → observe → think 的状态图。"""
    graph = StateGraph(AgentState)
    graph.add_node("think", runner.think)
    graph.add_node("act", runner.act)
    graph.add_node("observe", runner.observe)
    graph.add_edge(START, "think")
    graph.add_conditional_edges("think", _route_after_think)
    graph.add_edge("act", "observe")
    graph.add_edge("observe", "think")
    return graph.compile()


_ARGS_MAX_CHARS = 2000


def _short_args(arguments: Any) -> Any:
    """把工具参数收成可 JSON 序列化的短对象。"""
    if isinstance(arguments, str):
        text = arguments.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"raw": arguments[:_ARGS_MAX_CHARS]}
        arguments = parsed
    if arguments is None:
        return {}
    try:
        encoded = json.dumps(arguments, ensure_ascii=False)
    except TypeError:
        return {"raw": str(arguments)[:_ARGS_MAX_CHARS]}
    if len(encoded) <= _ARGS_MAX_CHARS:
        return arguments if not isinstance(arguments, str) else encoded
    return {"truncated": encoded[:_ARGS_MAX_CHARS]}


def _tool_output_failed(output: Any) -> bool:
    """注册表返回的字符串是否表示失败或取消。"""
    if not isinstance(output, str):
        return False
    return (
        output.startswith("工具错误")
        or output.startswith("已取消")
        or output.startswith("截图失败")
        or output.startswith("键鼠")
        or output.startswith("拒绝")
    )


def _tool_message_failed(message: dict[str, Any]) -> bool:
    """观察阶段的 tool 消息是否失败。"""
    content = message.get("content")
    if isinstance(content, dict):
        exec_info = content.get("exec")
        if isinstance(exec_info, dict) and exec_info.get("error"):
            return True
        return _tool_output_failed(str(content.get("text") or ""))
    return _tool_output_failed(content)


def _last_assistant_text(messages: list[dict[str, Any]]) -> str:
    """最近一条助手消息的文本，供计划规则使用。"""
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, dict):
            return str(content.get("text") or "")
        return str(content or "")
    return ""


def _route_after_think(state: AgentState) -> Literal["act", "__end__"]:
    """Think 之后：`acting` 去 Act，否则结束。"""
    if state.get("status") == "acting":
        return "act"
    return END


def _message_to_state(message: SessionMessage) -> dict[str, Any]:
    """会话消息转图状态消息，抬出 `tool_calls` / `tool_call_id`。"""
    item: dict[str, Any] = {"role": message.role, "content": message.content}
    if message.content.get("tool_calls"):
        item["tool_calls"] = message.content["tool_calls"]
    if message.content.get("tool_call_id"):
        item["tool_call_id"] = message.content["tool_call_id"]
    return item


def _state_to_session_message(item: dict[str, Any]) -> SessionMessage:
    """图状态消息压回可落盘的 `SessionMessage`。"""
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
