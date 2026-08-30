"""LangGraph ReAct：Think 调模型，Act 调工具，Observe 把结果写回消息。"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from max_gui.agent.context import (
    TaskContext,
    add_ui_candidates,
    append_action_summary,
    clear_grounded_facts,
    conversation_observation_path,
    latest_observation_path,
    locate_label,
    new_task_context,
    record_cursor_verification,
    register_completion_declaration,
    register_expectation,
    replace_desktop_snapshot,
    replace_locate_facts,
    replace_ui_snapshot,
    require_completion,
    restore_task_context,
    task_context_message,
    update_recovery,
    update_task_context,
    verify_completion,
    verify_current_expectation,
)
from max_gui.agent.plan import advance_subtask_after_tools, ingest_assistant_plan
from max_gui.agent.prompts import compose_gui_system_prompt
from max_gui.agent.state import AgentState
from max_gui.config import Settings
from max_gui.desktop.observation import observe_desktop_identity
from max_gui.inference.budget import ContextSelection, select_context_chains
from max_gui.inference.client import ChatDelta, InferenceClient, to_chat_messages
from max_gui.inference.retry import RetryNotice
from max_gui.observability import RunEvent, RunEventType, RunRecorder, safe_error_summary
from max_gui.session.store import Session, SessionMessage, SessionStore
from max_gui.tools.desktop import (
    active_view_frame,
    clear_desktop_context,
    current_session_id,
    restore_desktop_context,
    snapshot_desktop_context,
)
from max_gui.tools.protocol import ToolResult
from max_gui.tools.registry import ToolRegistry

ITERATION_LIMIT_MESSAGE = "已达到最大迭代次数，本回合停止。"
RECOVERY_LIMIT = 2
DISABLED_AGENT_TOOLS = frozenset({"locate"})
STRUCTURED_SIDE_EFFECTS = frozenset(
    {
        "click",
        "double_click",
        "type_text",
        "select_option",
        "set_file_input",
        "scroll",
        "open_url",
        "press_key",
        "press_shortcut",
        "drag",
        "activate_app",
    }
)


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
        self._on_event: Callable[[RunEvent], None] | None = None
        self._on_evaluation_step: Callable[[dict[str, Any]], None] | None = None
        self._tool_guard: Callable[[str, dict[str, Any]], str | None] | None = None
        self._session: Session | None = None
        self._recorder: RunRecorder | None = None
        self._last_status: str | None = None
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
        on_event: Callable[[RunEvent], None] | None = None,
        on_evaluation_step: Callable[[dict[str, Any]], None] | None = None,
        tool_guard: Callable[[str, dict[str, Any]], str | None] | None = None,
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
            on_event: 结构化运行事件回调；观察者异常不会进入 Agent 控制流。
            on_evaluation_step: 仅评测模式使用的动作回调，接收解析参数与截图关联。
            tool_guard: 仅评测模式使用的动作前护栏；返回原因时不执行对应工具。

        返回：
            终态 `AgentState`。
        """
        self.clear_interrupt()
        self._on_token = on_token
        self._on_reasoning = on_reasoning
        self._on_status = on_status
        self._on_message = on_message
        self._on_event = on_event
        self._on_evaluation_step = on_evaluation_step
        self._tool_guard = tool_guard
        self._last_status = None
        token = current_session_id.set(session.id)
        self._session = session
        restore_desktop_context(session.view_frame, session.locate_hits)
        checkpoint_run_id = None
        if resume and session.checkpoint:
            raw_run_id = session.checkpoint.get("run_id")
            if isinstance(raw_run_id, str) and raw_run_id:
                checkpoint_run_id = raw_run_id
        self._recorder = RunRecorder(
            self.settings.project_root / "artifacts" / "runs",
            session.id,
            run_id=checkpoint_run_id,
            on_event=on_event,
        )
        try:
            if resume and session.checkpoint:
                state: AgentState = dict(session.checkpoint)  # type: ignore[assignment]
                cursor = session.checkpoint.get("message_cursor")
                if isinstance(cursor, int) and 0 <= cursor <= len(session.messages):
                    state["messages"] = [
                        _message_to_state(item) for item in session.messages[:cursor]
                    ]
                elif "messages" not in state:
                    state["messages"] = [_message_to_state(item) for item in session.messages]
                state["session_id"] = session.id
                state["run_id"] = self._recorder.run_id
                state["history_message_count"] = int(state.get("history_message_count") or 0)
                state["task_context"] = restore_task_context(
                    state.get("task_context") or session.task_context,
                    list(state.get("messages") or []),
                )
            else:
                if user_text is not None:
                    _capture_conversation_context(session)
                    clear_desktop_context()
                    session.view_frame = None
                    session.locate_hits = {}
                messages: list[dict[str, Any]] = []
                history_message_count = len(session.messages)
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
                    "run_id": self._recorder.run_id,
                    "messages": messages,
                    "images": list(image_paths or []),
                    "pending_tool_calls": [],
                    "iteration": 0,
                    "status": "thinking",
                    "error": None,
                    "plan": [],
                    "current_subtask": None,
                    "task_context": new_task_context(
                        user_text or "", image_paths or [], session.conversation_context
                    ),
                    "history_message_count": history_message_count,
                    "allowed_tools": [],
                    "context_diagnostics": {},
                }

            unfinished = self._recorder.unfinished_tools
            run_event: RunEventType = "run.resumed" if checkpoint_run_id else "run.started"
            self._emit_event(
                run_event,
                state,
                {
                    "provider": self.settings.provider,
                    "model": self.settings.model_name,
                    "max_iterations": self.settings.max_iterations,
                    "legacy_checkpoint": bool(
                        resume and session.checkpoint and not checkpoint_run_id
                    ),
                    "unfinished_tools": [
                        {"call_id": call_id, "tool_name": name}
                        for call_id, name in unfinished.items()
                    ],
                },
            )
            self._emit_status(str(state.get("status") or "thinking"), state)

            try:
                state = await self._prime_ui_observation(state)
                result = await self._graph.ainvoke(state)
            except Exception as exc:
                self._emit_event(
                    "run.failed",
                    state,
                    {
                        **self._run_summary("error"),
                        "error": safe_error_summary(exc),
                    },
                )
                raise
            self._emit_status(str(result.get("status") or "done"), result)
            self._persist(session, result)
            self._emit_terminal(result)
            return result
        finally:
            self._flush_desktop_context()
            if self._recorder is not None:
                self._recorder.close()
            self._recorder = None
            self._session = None
            current_session_id.reset(token)

    async def _prime_ui_observation(self, state: AgentState) -> AgentState:
        """在首轮 Think 前建立当前截图与结构化 UI 快照。

        返回：带最新截图、桌面身份和 browser/native UI 摘要的状态；浏览器或 AX
        不可用时保留视觉后备，不阻断任务启动。副作用：会截取一张当前屏幕，并
        让受控浏览器页在非原生模态场景下置前以保证 DOM 与截图属于同一界面。
        """
        context = _task_context(state)
        desktop_observation = observe_desktop_identity()
        native_elements = self.registry.macos_ax.observe() if self.registry.macos_ax else []
        active_dialog = desktop_observation.get("active_dialog") or {}
        has_native_modal = bool(active_dialog.get("id") or active_dialog.get("name"))
        if not has_native_modal and not native_elements and self.registry.browser is not None:
            # 先置受控页，再截图；否则 DOM 可能来自受控 Chrome，而截图仍是用户浏览器。
            await self.registry.browser.observe()
        output = await self.registry.invoke("screenshot", {})
        if not isinstance(output, ToolResult) or not output.ok or not output.images:
            return state
        frame = active_view_frame()
        if frame is None or not frame.image_path.is_file():
            return state
        # 置前受控页可能改变前台应用；必须用截图同一时刻的身份选择通道。
        desktop_observation = observe_desktop_identity()
        context["latest_observation"] = {"path": str(output.images[-1]), "source": "tool"}
        context = replace_desktop_snapshot(
            context, frame_path=str(frame.image_path), observation=desktop_observation
        )
        context = await self._replace_structured_ui_snapshot(
            context,
            frame_path=str(frame.image_path),
            desktop_observation=desktop_observation,
        )
        return {**state, "task_context": context}

    async def think(self, state: AgentState) -> AgentState:
        """调用模型。有工具调用则进入 `acting`，否则 `done`；超迭代或推理失败为 `error`。

        拼装完成后立即写入会话并回调 `on_message`。推理异常不抛出图外。
        """
        if self._interrupt.is_set():
            return {**state, "status": "interrupted"}
        if state.get("status") == "error":
            return state
        self._emit_status("thinking", state)
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

        context = update_task_context(
            _task_context(state),
            status="thinking",
            plan=list(state.get("plan") or []),
            current_subtask=state.get("current_subtask"),
        )
        inline_image = latest_observation_path(context) or conversation_observation_path(context)
        system_prompt = compose_gui_system_prompt(frame=active_view_frame())
        allowed_tools = _allowed_tool_names(context, self.registry)
        tool_schemas = _model_tool_schemas(self.registry, allowed_tools)
        model_started = time.perf_counter()
        try:
            selection = _select_model_context(
                state,
                context=context,
                system=system_prompt,
                tools=tool_schemas,
                inline_image=inline_image,
                settings=self.settings,
            )
        except Exception as exc:
            failed_state: AgentState = {
                **state,
                "task_context": context,
                "allowed_tools": sorted(allowed_tools),
            }
            self._emit_event(
                "model.failed",
                failed_state,
                {
                    "provider": self.settings.provider,
                    "model": self.settings.model_name,
                    "duration_ms": int((time.perf_counter() - model_started) * 1000),
                    "error": safe_error_summary(exc),
                    "error_type": type(exc).__name__,
                    "attempt_count": 0,
                    "retry_count": 0,
                },
            )
            return {
                **failed_state,
                "status": "error",
                "error": str(exc),
                "pending_tool_calls": [],
            }
        context_diagnostics = _selection_diagnostics(
            state,
            context=context,
            selection=selection,
            inline_image=inline_image,
            tool_count=len(tool_schemas),
            settings=self.settings,
        )
        state = {
            **state,
            "task_context": context,
            "allowed_tools": sorted(allowed_tools),
            "context_diagnostics": context_diagnostics,
        }
        self._emit_event(
            "model.started",
            state,
            {
                "provider": self.settings.provider,
                "model": self.settings.model_name,
                **context_diagnostics,
            },
        )
        try:
            encoded = to_chat_messages(
                selection.messages,
                settings=self.settings,
                system=system_prompt,
                inline_image_path=inline_image,
            )
            delta: ChatDelta = await self.client.stream(
                encoded,
                tools=tool_schemas,
                on_token=self._on_token,
                on_reasoning=self._on_reasoning,
                should_stop=self._interrupt.is_set,
                on_retry=lambda notice: self._emit_model_retry(state, notice),
            )
        except Exception as exc:
            metadata = getattr(exc, "metadata", None)
            self._emit_event(
                "model.failed",
                state,
                {
                    "provider": self.settings.provider,
                    "model": self.settings.model_name,
                    "duration_ms": int((time.perf_counter() - model_started) * 1000),
                    "error": safe_error_summary(exc),
                    "error_type": type(exc).__name__,
                    "attempt_count": metadata.attempt_count if metadata else 0,
                    "retry_count": metadata.retry_count if metadata else 0,
                },
            )
            return {
                **state,
                "status": "error",
                "error": str(exc),
                "pending_tool_calls": [],
            }
        if self._interrupt.is_set() or delta.finish_reason == "interrupted":
            messages = list(state.get("messages") or [])
            message_index: int | None = None
            if delta.text or delta.reasoning:
                assistant = {"role": "assistant", "content": _assistant_content(delta)}
                messages.append(assistant)
                message_index = self._commit_message(assistant)
            self._emit_model_completed(state, delta, model_started, message_index)
            return {
                **state,
                "messages": messages,
                "status": "interrupted",
                "task_context": update_task_context(
                    context,
                    status="interrupted",
                    plan=list(state.get("plan") or []),
                    current_subtask=state.get("current_subtask"),
                ),
            }

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
        message_index = self._commit_message(assistant)
        self._emit_model_completed(state, delta, model_started, message_index)
        if delta.tool_calls:
            return {
                **state,
                "messages": messages,
                "pending_tool_calls": delta.tool_calls,
                "status": "acting",
                "plan": plan,
                "current_subtask": current,
                "task_context": update_task_context(
                    context, status="acting", plan=plan, current_subtask=current
                ),
            }
        if context.get("completion_required") and not context.get("completion_verified"):
            return {
                **state,
                "messages": messages,
                "pending_tool_calls": [],
                "iteration": int(state.get("iteration") or 0) + 1,
                "status": "thinking",
                "plan": plan,
                "current_subtask": current,
                "task_context": update_task_context(
                    context, status="thinking", plan=plan, current_subtask=current
                ),
            }
        return {
            **state,
            "messages": messages,
            "pending_tool_calls": [],
            "status": "done",
            "plan": plan,
            "current_subtask": current,
            "task_context": update_task_context(
                context, status="done", plan=plan, current_subtask=current
            ),
        }

    async def act(self, state: AgentState) -> AgentState:
        """依次执行 `pending_tool_calls`，每完成一个即落盘并回调 `on_message`。"""
        if self._interrupt.is_set():
            return {**state, "status": "interrupted"}
        self._emit_status("acting", state)
        results: list[dict[str, Any]] = []
        context = _task_context(state)
        allowed_tools = set(state.get("allowed_tools") or [])
        side_effect_seen = False
        for call in state.get("pending_tool_calls") or []:
            if self._interrupt.is_set():
                return {**state, "status": "interrupted"}
            fn = call.get("function") or {}
            name = str(fn.get("name") or "")
            call_id = str(call.get("id") or name)
            arguments = _tool_arguments(fn.get("arguments"))
            expectation = arguments.pop("expectation", None)
            frame_before = _active_frame_path()
            target_label = _target_label_for_move(context, name, arguments, frame_before)
            side_effect = self.registry.is_side_effect(name)
            self._emit_event(
                "tool.started",
                state,
                {
                    "call_id": call_id,
                    "tool_name": name,
                    "argument_chars": _argument_chars(fn.get("arguments")),
                },
            )
            started = time.perf_counter()
            blocked_fingerprint = _blocked_fingerprint(context, name, arguments)
            if blocked_fingerprint:
                output = ToolResult(
                    text="该工具调用已被恢复护栏阻断，请先获取新截图或切换观察策略。",
                    ok=False,
                    code="recovery_blocked",
                )
            elif side_effect_seen:
                output: str | ToolResult = ToolResult(
                    text=(
                        "本轮已有副作用工具；后续调用已阻断。下一次只提交一个副作用调用，"
                        "并先阅读该动作后的截图再决定点击或继续操作。"
                    ),
                    ok=False,
                    code="action_batch_blocked",
                )
            elif name not in allowed_tools:
                output = ToolResult(
                    text=f"当前 Agent 阶段未开放工具：{name}",
                    ok=False,
                    code="tool_not_available",
                )
            elif self._tool_guard and (guard_reason := self._tool_guard(name, arguments)):
                output = ToolResult(text=guard_reason, ok=False, code="evaluation_safety_blocked")
            else:
                output = await self.registry.invoke(name, arguments)
            if name in STRUCTURED_SIDE_EFFECTS and isinstance(output, ToolResult) and output.ok:
                # 结构化动作同样必须产生一张独立后置截图，不能把 locator 成功当成任务成功。
                post_observation = await self.registry.invoke("screenshot", {})
                if isinstance(post_observation, ToolResult) and post_observation.ok:
                    output.images.extend(post_observation.images)
            if side_effect:
                side_effect_seen = True
            duration_ms = int((time.perf_counter() - started) * 1000)
            has_image = False
            error: str | None = None
            result_code = "ok"
            if isinstance(output, ToolResult):
                text = output.text
                images = [{"path": str(path)} for path in output.images]
                has_image = bool(output.images)
                result_code = output.code
                if not output.ok:
                    error = output.text
            else:
                text = str(output)
                images = []
                if _tool_output_failed(output):
                    error = str(output)
                    result_code = "tool_error"
            if (
                name == "task_complete"
                and error is None
                and not _completion_evidence_ready(context)
            ):
                text = "任务完成声明已登记，但需要声明后的新截图进行独立核验。"
                result_code = "completion_pending"
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
                    "ok": error is None,
                    "code": result_code,
                    "has_image": has_image,
                },
            }
            item = {
                "role": "tool",
                "content": content,
                "tool_call_id": call_id,
                "name": name,
            }
            results.append(item)
            image_path = str(images[-1]["path"]) if images else None
            context = append_action_summary(
                context,
                name=name,
                arguments=fn.get("arguments"),
                error=error,
                has_observation=has_image,
                conclusion=_action_conclusion(name, text),
                image_path=image_path,
            )
            context = _update_grounded_facts_after_tool(
                context,
                name=name,
                arguments=arguments,
                text=text,
                error=error,
                image_path=image_path,
                frame_before=frame_before,
                target_label=target_label,
            )
            if side_effect and error is None:
                context = require_completion(context)
                context = register_expectation(context, expectation, source_frame_path=frame_before)
            if name == "task_complete" and error is None:
                context = register_completion_declaration(
                    context,
                    summary=str(arguments.get("summary") or ""),
                    evidence=str(arguments.get("evidence") or ""),
                    observed_path=latest_observation_path(context),
                )
            message_index = self._commit_message(item)
            event_type: RunEventType = "tool.failed" if error else "tool.completed"
            event_data: dict[str, Any] = {
                "call_id": call_id,
                "tool_name": name,
                "duration_ms": duration_ms,
                "session_message_index": message_index,
                "has_image": has_image,
                "image_count": len(images),
                "outcome": "failed" if error else "success",
                "code": result_code,
            }
            if error:
                event_data["error"] = safe_error_summary(error)
            self._emit_event(event_type, state, event_data)
            self._emit_evaluation_step(
                {
                    "tool_name": name,
                    "arguments": arguments,
                    "images": [str(item["path"]) for item in images],
                    "text": text,
                    "ok": error is None,
                    "code": result_code,
                    "iteration": int(state.get("iteration") or 0),
                    "message_index": message_index,
                    "reasoning": _last_assistant_reasoning(list(state.get("messages") or [])),
                }
            )
            if name == "task_complete" and error is None:
                # 完成声明必须紧接一次独立截图；这一步不依赖模型是否再次请求工具。
                post_output = await self.registry.invoke("screenshot", {})
                if isinstance(post_output, ToolResult):
                    post_images = [{"path": str(path)} for path in post_output.images]
                    post_text = post_output.text
                    post_ok = post_output.ok
                    post_code = post_output.code
                else:
                    post_images = []
                    post_text = str(post_output)
                    post_ok = True
                    post_code = "ok"
                post_item = {
                    "role": "tool",
                    "content": {
                        "text": post_text,
                        "images": post_images,
                        "name": "screenshot",
                        "exec": {
                            "iteration": int(state.get("iteration") or 0),
                            "arguments": {},
                            "duration_ms": 0,
                            "error": None if post_ok else post_text,
                            "ok": post_ok,
                            "code": post_code,
                            "has_image": bool(post_images),
                        },
                    },
                    "tool_call_id": f"{call_id}:post-screenshot",
                    "name": "screenshot",
                }
                results.append(post_item)
                post_index = self._commit_message(post_item)
                self._emit_evaluation_step(
                    {
                        "tool_name": "screenshot",
                        "arguments": {},
                        "images": [str(item["path"]) for item in post_images],
                        "text": post_text,
                        "ok": post_ok,
                        "code": post_code,
                        "iteration": int(state.get("iteration") or 0),
                        "message_index": post_index,
                        "reasoning": None,
                        "completion_post_observation": True,
                    }
                )
        self._flush_desktop_context()
        return {
            **state,
            "pending_tool_calls": results,
            "status": "observing",
            "task_context": update_task_context(
                context,
                status="observing",
                plan=list(state.get("plan") or []),
                current_subtask=state.get("current_subtask"),
            ),
        }

    async def observe(self, state: AgentState) -> AgentState:
        """把工具结果追加到消息，迭代计数加一，回到 `thinking`。"""
        self._emit_status("observing", state)
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
        context = _task_context(state)
        current_frame = _active_frame_path()
        if current_frame and Path(current_frame).is_file():
            desktop_observation = observe_desktop_identity()
            context = replace_desktop_snapshot(
                context, frame_path=current_frame, observation=desktop_observation
            )
            context = await self._replace_structured_ui_snapshot(
                context,
                frame_path=current_frame,
                desktop_observation=desktop_observation,
            )
            for item in tool_messages:
                if item.get("name") != "locate" or not isinstance(item.get("content"), dict):
                    continue
                try:
                    payload = json.loads(str(item["content"].get("text") or ""))
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get("observation_only") is False:
                    context = add_ui_candidates(
                        context,
                        frame_path=current_frame,
                        candidates=payload.get("items"),
                        source="locate",
                    )
            context = verify_current_expectation(
                context,
                previous_frame_path=(context.get("current_expectation") or {}).get(
                    "source_frame_path"
                ),
            )
        completion_verified = bool(context.get("completion_verified"))
        declaration = context.get("completion_declaration") or {}
        if declaration and not completion_verified:
            post = next(
                (
                    item
                    for item in tool_messages
                    if isinstance(item.get("content"), dict)
                    and item.get("name") == "screenshot"
                    and item["content"].get("exec", {}).get("ok")
                    and item["content"].get("images")
                ),
                None,
            )
            if post:
                path = str(post["content"]["images"][-1].get("path") or "")
                if (
                    path
                    and Path(path).is_file()
                    and str(declaration.get("evidence") or "").strip()
                    and _required_progress_verified(context)
                ):
                    context = verify_completion(
                        context,
                        summary=str(declaration.get("summary") or "独立后置观察通过"),
                        observation_path=path,
                    )
                    completion_verified = True
                else:
                    context = _completion_verification_failed(
                        context, "后置截图不可用、声明证据不足或必经进度尚未验证"
                    )
            elif any(item.get("name") == "task_complete" for item in tool_messages):
                context = _completion_verification_failed(context, "完成声明后必须获取新的截图")
            completion_verified = bool(context.get("completion_verified"))
        context = _update_recovery_after_observation(context, tool_messages)
        recovery = context.get("recovery") or {}
        exhausted = int(recovery.get("failure_count") or 0) >= RECOVERY_LIMIT
        next_state: AgentState = {
            **state,
            "messages": messages,
            "pending_tool_calls": [],
            "iteration": int(state.get("iteration") or 0) + 1,
            "status": "error" if exhausted else ("done" if completion_verified else "thinking"),
            "error": "recovery_exhausted" if exhausted else state.get("error"),
            "plan": plan,
            "current_subtask": current,
            "task_context": update_task_context(
                context,
                status="error" if exhausted else ("done" if completion_verified else "thinking"),
                plan=plan,
                current_subtask=current,
            ),
        }
        captured_images = 0
        for item in tool_messages:
            content = item.get("content")
            if isinstance(content, dict) and isinstance(content.get("images"), list):
                captured_images += len(content["images"])
        self._emit_event(
            "observation.completed",
            next_state,
            {
                "tool_count": len(tool_messages),
                "tool_failed": failed,
                "post_action_observation_captured": captured_images > 0,
                "image_count": captured_images,
                "business_verified": completion_verified,
                "completion_required": bool(context.get("completion_required")),
                "completion_verified": completion_verified,
                "terminal_reason": "recovery_exhausted" if exhausted else None,
            },
        )
        return next_state

    async def _replace_structured_ui_snapshot(
        self,
        context: TaskContext,
        *,
        frame_path: str,
        desktop_observation: dict[str, Any],
    ) -> TaskContext:
        """按原生模态、受控浏览器、视觉后备顺序刷新唯一 UI 快照。

        原生对话框优先于网页 DOM，以避免文件选择器或权限窗口被同名网页控件覆盖。
        每次调用均替换 `UIRegistry` 当前版本，使上一次的元素引用立即失效。
        """
        active_dialog = desktop_observation.get("active_dialog") or {}
        native_elements = self.registry.macos_ax.observe() if self.registry.macos_ax else []
        has_native_modal = bool(active_dialog.get("id") or active_dialog.get("name"))
        active_app = (desktop_observation.get("active_app") or {}).get("name")
        chrome_is_frontmost = "chrome" in str(active_app or "").casefold()
        if native_elements and (has_native_modal or not chrome_is_frontmost):
            snapshot = self.registry.ui_registry.replace(
                frame_path=frame_path, context="native", elements=native_elements
            )
            return replace_ui_snapshot(context, snapshot.summary())
        if self.registry.browser is not None:
            browser_observation = await self.registry.browser.observe()
            if browser_observation is not None:
                url, elements = browser_observation
                snapshot = self.registry.ui_registry.replace(
                    frame_path=frame_path, context="browser", elements=elements, url=url
                )
                return replace_ui_snapshot(context, snapshot.summary())
        if native_elements:
            snapshot = self.registry.ui_registry.replace(
                frame_path=frame_path, context="native", elements=native_elements
            )
            return replace_ui_snapshot(context, snapshot.summary())
        self.registry.ui_registry.clear()
        return replace_ui_snapshot(context, None)

    def _flush_desktop_context(self) -> None:
        """把当前视图坐标系与定位表写入会话并落盘。"""
        session = self._session
        if session is None:
            return
        frame, hits = snapshot_desktop_context()
        if frame is not None:
            session.view_frame = frame
        session.locate_hits = hits
        self.store.save(session)

    def _emit_evaluation_step(self, payload: dict[str, Any]) -> None:
        """向显式评测回调发送高保真动作，不扩展普通运行 JSONL。

        参数：`payload` 仅在调用方提供回调时发送；回调异常被隔离，不能影响 Agent 控制流。
        """
        if self._on_evaluation_step is None:
            return
        try:
            self._on_evaluation_step(payload)
        except Exception:
            return

    def _emit_status(self, status: str, state: AgentState) -> None:
        """通知调用方当前状态，并为真实迁移发出结构化事件。"""
        if self._on_status:
            self._on_status(status)
        previous = self._last_status
        if previous == status:
            return
        self._last_status = status
        self._emit_event("state.changed", state, {"from": previous, "to": status})

    def _commit_message(self, item: dict[str, Any]) -> int | None:
        """把图消息写入会话并通知 TUI，返回追加后的稳定消息下标。"""
        session_msg = _state_to_session_message(item)
        session = self._session
        message_index: int | None = None
        if session is not None:
            self.store.append_messages(session, [session_msg])
            message_index = len(session.messages) - 1
        if self._on_message:
            self._on_message(session_msg.role, session_msg.content)
        return message_index

    def _emit_event(
        self,
        event_type: RunEventType,
        state: AgentState,
        data: dict[str, Any] | None = None,
    ) -> RunEvent | None:
        """把当前图上下文收进记录器；无记录器时安全跳过。"""
        recorder = self._recorder
        if recorder is None:
            return None
        return recorder.record(
            event_type,
            iteration=int(state.get("iteration") or 0),
            subtask=state.get("current_subtask"),
            data=data,
        )

    def _emit_model_completed(
        self,
        state: AgentState,
        delta: ChatDelta,
        started: float,
        message_index: int | None,
    ) -> None:
        """记录一次模型调用汇总，不复制正文或 reasoning 原文。"""
        data: dict[str, Any] = {
            "provider": self.settings.provider,
            "model": self.settings.model_name,
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "finish_reason": delta.finish_reason,
            "text_chars": len(delta.text),
            "reasoning_chars": len(delta.reasoning),
            "tool_call_count": len(delta.tool_calls),
            "session_message_index": message_index,
            "attempt_count": delta.attempt_count,
            "retry_count": delta.retry_count,
            **dict(state.get("context_diagnostics") or {}),
        }
        if delta.usage is not None:
            data["prompt_tokens"] = delta.usage.prompt_tokens
            data["completion_tokens"] = delta.usage.completion_tokens
            data["total_tokens"] = delta.usage.total_tokens
        self._emit_event("model.completed", state, data)

    def _emit_model_retry(self, state: AgentState, notice: RetryNotice) -> None:
        """把客户端安全重试通知转成一次结构化运行事件。"""
        data: dict[str, Any] = {
            "attempt": notice.attempt,
            "max_attempts": notice.max_attempts,
            "reason_code": notice.reason_code,
            "delay_ms": notice.delay_ms,
            "error": safe_error_summary(notice.error),
        }
        if notice.status_code is not None:
            data["status_code"] = notice.status_code
        self._emit_event("model.retrying", state, data)

    def _run_summary(self, final_status: str) -> dict[str, Any]:
        """返回当前记录器汇总；记录器缺失时给最小终态。"""
        if self._recorder is None:
            return {"final_status": final_status}
        return self._recorder.summary(final_status=final_status)

    def _historical_message_count(self, state: AgentState) -> int:
        """计算未进入当前任务推理上下文的会话消息数量。"""
        return max(0, int(state.get("history_message_count") or 0))

    def _emit_terminal(self, state: AgentState) -> None:
        """按 Agent 终态发出对应运行终态和统计。"""
        status = str(state.get("status") or "done")
        event_type: RunEventType
        if status == "interrupted":
            event_type = "run.interrupted"
        elif status == "error":
            event_type = "run.failed"
        else:
            event_type = "run.completed"
        data = self._run_summary(status)
        data["run_id"] = self._recorder.run_id if self._recorder else state.get("run_id")
        data["terminal_reason"] = _terminal_reason(status, state)
        if state.get("error"):
            data["error"] = safe_error_summary(str(state["error"]))
        self._emit_event(event_type, state, data)
        if self._session is not None:
            self._session.run_summary = dict(data)
            self.store.save(self._session)

    def _persist(self, session: Session, state: AgentState) -> None:
        """写回 status、checkpoint、桌面坐标系；尚未落盘的消息才追加。"""
        session.status = str(state.get("status") or "done")
        checkpoint = {key: value for key, value in dict(state).items() if key != "messages"}
        checkpoint["message_cursor"] = len(session.messages)
        session.checkpoint = checkpoint
        session.task_context = dict(
            update_task_context(
                _task_context(state),
                status=session.status,
                plan=list(state.get("plan") or []),
                current_subtask=state.get("current_subtask"),
            )
        )
        frame, hits = snapshot_desktop_context()
        if frame is not None:
            session.view_frame = frame
        session.locate_hits = hits
        known = len(session.messages)
        extras = list(state.get("messages") or [])[known:]
        if extras:
            self.store.append_messages(
                session, [_state_to_session_message(item) for item in extras]
            )
        if session.checkpoint is not None:
            session.checkpoint["message_cursor"] = len(session.messages)
        self.store.save(session)


def _assistant_content(delta: ChatDelta) -> dict[str, Any]:
    """从流式回复收成助手 content；有思考才写 `reasoning`。"""
    payload: dict[str, Any] = {"text": delta.text}
    if delta.reasoning:
        payload["reasoning"] = delta.reasoning
    return payload


def _terminal_reason(status: str, state: AgentState) -> str:
    """把图状态投影为稳定的运行终态原因。"""
    if status == "interrupted":
        return "user_interrupted"
    if status == "error":
        if str(state.get("error") or "") == "recovery_exhausted":
            return "recovery_exhausted"
        if str(state.get("error") or "") == ITERATION_LIMIT_MESSAGE:
            return "iteration_limit"
        return "inference_failed" if str(state.get("error") or "").strip() else "error"
    return "completed"


def _build_graph(runner: AgentRunner):
    """编译 START → think ⇄ act → observe → think 的状态图。"""
    graph = StateGraph(AgentState)
    graph.add_node("think", runner.think)
    graph.add_node("act", runner.act)
    graph.add_node("observe", runner.observe)
    graph.add_edge(START, "think")
    graph.add_conditional_edges("think", _route_after_think)
    graph.add_edge("act", "observe")
    graph.add_conditional_edges("observe", _route_after_observe)
    return graph.compile()


_ARGS_MAX_CHARS = 2000


def _argument_chars(arguments: Any) -> int:
    """返回原始工具参数的字符数，只供运行诊断且不保存正文。"""
    if arguments is None:
        return 0
    if isinstance(arguments, str):
        return len(arguments)
    try:
        return len(json.dumps(arguments, ensure_ascii=False))
    except TypeError:
        return len(str(arguments))


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


def _last_assistant_reasoning(messages: list[dict[str, Any]]) -> str | None:
    """提取当前动作关联的最近模型推理，仅供显式评测回调使用。"""
    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, dict):
            reasoning = str(content.get("reasoning") or "").strip()
            return reasoning or None
    return None


def _task_context(state: AgentState) -> TaskContext:
    """取得当前任务胶囊；旧 checkpoint 缺字段时即时构造兼容版本。"""
    return restore_task_context(state.get("task_context"), list(state.get("messages") or []))


def _select_model_context(
    state: AgentState,
    *,
    context: TaskContext,
    system: str,
    tools: list[dict[str, Any]],
    inline_image: str | None,
    settings: Settings,
) -> ContextSelection:
    """按主推理预算选择当前用户消息和最近完整工具链。"""
    messages = list(state.get("messages") or [])
    user = _task_user_message(messages, context)
    chains = _completed_tool_chains(messages)
    return select_context_chains(
        user_message=user,
        chains=chains,
        system=system,
        tools=tools,
        has_inline_image=bool(inline_image and Path(inline_image).is_file()),
        settings=settings,
    )


def _task_user_message(messages: list[dict[str, Any]], context: TaskContext) -> dict[str, Any]:
    """构造模型可见的用户任务消息，并附带脱敏任务状态。"""
    original: dict[str, Any] | None = None
    for message in messages:
        if message.get("role") == "user":
            original = message
            break
    content = dict((original or {}).get("content") or {})
    instruction = str(context.get("user_instruction") or content.get("text") or "继续当前任务")
    content["text"] = (
        f"{instruction}\n\n{task_context_message(context, current_frame_path=_active_frame_path())}"
    )
    if not content.get("images") and not latest_observation_path(context):
        history = conversation_observation_path(context)
        if history and Path(history).is_file():
            content["images"] = [{"path": history}]
    return {"role": "user", "content": content}


def _capture_conversation_context(session: Session) -> None:
    """把上一回合最后一张可读图存为只读背景，不保留可执行坐标。"""
    frame = active_view_frame()
    if frame is None or not frame.image_path.is_file():
        return
    dialogue: list[str] = []
    for message in session.messages[-4:]:
        if message.role not in {"user", "assistant"}:
            continue
        text = str(message.content.get("text") or "").strip()
        if text:
            dialogue.append(text[:240])
    session.conversation_context = {
        "observation": {
            "path": str(frame.image_path),
            "source": "tool",
            "captured_at": session.updated_at,
        },
        "dialogue": dialogue[-2:],
    }


def _completed_tool_chains(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """按 assistant 调用与其所有已完成 tool 结果切分合法的上下文链。"""
    chains: list[list[dict[str, Any]]] = []
    index = 0
    while index < len(messages):
        assistant = messages[index]
        calls = assistant.get("tool_calls") if assistant.get("role") == "assistant" else None
        if not isinstance(calls, list) or not calls:
            index += 1
            continue
        call_ids = {str(call.get("id") or "") for call in calls}
        chain = [assistant]
        cursor = index + 1
        while cursor < len(messages) and messages[cursor].get("role") == "tool":
            tool = messages[cursor]
            if str(tool.get("tool_call_id") or "") not in call_ids:
                break
            chain.append(tool)
            cursor += 1
        if len(chain) > 1:
            chains.append(chain)
        index = cursor
    return chains


def _selection_diagnostics(
    state: AgentState,
    *,
    context: TaskContext,
    selection: ContextSelection,
    inline_image: str | None,
    tool_count: int,
    settings: Settings,
) -> dict[str, int | str | None]:
    """返回预算与裁剪计数，不复制消息、schema 或完成证据。"""
    return {
        "task_id": context.get("task_id"),
        "context_message_count": len(selection.messages),
        "context_inline_image_count": int(bool(inline_image and Path(inline_image).is_file())),
        "context_recent_action_count": len(context.get("action_history") or []),
        "context_excluded_message_count": max(0, int(state.get("history_message_count") or 0)),
        "context_window": settings.context_window,
        "context_max_output_tokens": settings.max_output_tokens,
        "context_safety_margin": settings.context_safety_margin,
        "context_estimated_input_tokens": selection.estimated_input_tokens,
        "context_available_input_tokens": selection.available_input_tokens,
        "context_dynamic_tool_count": tool_count,
        "context_included_chain_count": selection.included_chain_count,
        "context_excluded_chain_count": selection.excluded_chain_count,
    }


_INITIAL_TOOL_NAMES = {"prepare_image", "ocr", "screenshot", "screen_info"}


def _allowed_tool_names(context: TaskContext, registry: ToolRegistry) -> set[str]:
    """按当前任务有效截图与完成门返回实际可暴露工具名。"""
    frame = active_view_frame()
    frame_ready = bool(frame is not None and frame.image_path.is_file())
    if not frame_ready:
        return registry.names() & _INITIAL_TOOL_NAMES
    allowed = registry.names() - {"task_complete"} - DISABLED_AGENT_TOOLS
    if not context.get("ui_snapshot"):
        allowed -= {
            "click",
            "double_click",
            "type_text",
            "select_option",
            "set_file_input",
            "scroll",
            "open_url",
            "drag",
            "press_key",
            "press_shortcut",
            "activate_app",
        }
    recovery = context.get("recovery") or {}
    blocked = {str(item) for item in recovery.get("blocked_calls") or []}
    allowed -= blocked
    if context.get("completion_required") and not context.get("completion_verified"):
        allowed.add("task_complete")
    return allowed


def _model_tool_schemas(registry: ToolRegistry, allowed_tools: set[str]) -> list[dict[str, Any]]:
    """导出模型 schema，隐藏旧定位字段并为副作用动作附加受限预期。"""
    schemas = registry.schemas(allowed_tools)
    for schema in schemas:
        function = schema.get("function")
        if not isinstance(function, dict):
            continue
        parameters = function.get("parameters")
        if isinstance(parameters, dict) and isinstance(parameters.get("properties"), dict):
            properties = parameters["properties"]
            if function.get("name") in {"mouse_move", "mouse_scroll"}:
                properties.pop("target_id", None)
            if registry.is_side_effect(str(function.get("name") or "")):
                properties["expectation"] = {
                    "type": "object",
                    "description": "可选：此动作后应在新截图中验证的结果",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": [
                                "dialog_appears",
                                "active_window_changes",
                                "element_appears",
                                "element_disappears",
                                "element_selected",
                                "screen_changed",
                            ],
                        },
                        "target": {"type": "string"},
                        "progress_id": {"type": "string"},
                    },
                    "required": ["kind"],
                }
    return schemas


def _completion_verification_failed(context: TaskContext, reason: str) -> TaskContext:
    """保留待验证声明并记录失败原因，供下一轮模型修正。"""
    updated = dict(context)
    updated["completion_verified"] = False
    updated["completion_verification"] = {"ok": False, "conclusion": reason[:400]}
    return updated


def _required_progress_verified(context: TaskContext) -> bool:
    """确认所有标为必经的进度项已由观察验证，空列表不阻断兼容任务。"""
    return all(
        item.get("status") == "verified"
        for item in context.get("progress") or []
        if isinstance(item, dict) and item.get("required")
    )


def _update_recovery_after_observation(
    context: TaskContext, tool_messages: list[dict[str, Any]]
) -> TaskContext:
    """按工具错误码和当前帧更新恢复计数；成功截图清除旧护栏。"""
    batch_blocked = any(
        isinstance(item.get("content"), dict)
        and str((item["content"].get("exec") or {}).get("code") or "") == "action_batch_blocked"
        for item in tool_messages
    )
    if batch_blocked:
        return update_recovery(
            context,
            fingerprint="action_batch_blocked",
            frame_path=None,
            hint="上一回复包含多个副作用调用。下一次只提交一个副作用调用，并先观察动作后的截图。",
        )
    for item in tool_messages:
        content = item.get("content")
        if not isinstance(content, dict):
            continue
        execution = content.get("exec") or {}
        code = str(execution.get("code") or "")
        name = str(item.get("name") or "")
        frame = _active_frame_path()
        if name == "screenshot" and execution.get("ok"):
            context = update_recovery(
                context, fingerprint=None, frame_path=frame, hint=None, increment=False
            )
            continue
        if not execution.get("error"):
            continue
        arguments = _short_args(execution.get("arguments"))
        text_value = str(content.get("text") or "")
        is_coordinate_failure = "坐标" in text_value or (
            code in {"tool_error", "recovery_blocked"} and name.startswith("mouse_")
        )
        if not is_coordinate_failure:
            continue
        fingerprint = f"{name}:{code}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True)}"
        hint = "请先获取新截图，并使用该截图内的视图像素重新移动鼠标。"
        blocked = list((context.get("recovery") or {}).get("blocked_calls") or [])
        if (
            fingerprint not in blocked
            and int((context.get("recovery") or {}).get("failure_count") or 0) >= 1
        ):
            blocked.append(fingerprint)
        context = update_recovery(
            context, fingerprint=fingerprint, frame_path=frame, hint=hint, blocked_calls=blocked
        )
    return context


def _blocked_fingerprint(context: TaskContext, name: str, arguments: dict[str, Any]) -> str | None:
    """返回当前调用是否命中已记录的失败指纹。"""
    recovery = context.get("recovery") or {}
    encoded = json.dumps(_short_args(arguments), ensure_ascii=False, sort_keys=True)
    fingerprint = f"{name}:{encoded}"
    for blocked in recovery.get("blocked_calls") or []:
        if str(blocked).startswith(f"{name}:") and (
            str(blocked).endswith(encoded) or str(blocked) == fingerprint
        ):
            return str(blocked)
    return None


def _completion_evidence_ready(context: TaskContext) -> bool:
    """最近一次成功副作用本身或其后是否取得了后置截图。"""
    side_effects = {
        "mouse_move",
        "mouse_click",
        "mouse_drag",
        "mouse_scroll",
        "keyboard_type",
        "keyboard_press",
    }
    history = list(context.get("action_history") or [])
    last_side_effect = -1
    for index, item in enumerate(history):
        if item.get("name") in side_effects and item.get("outcome") == "success":
            last_side_effect = index
    if last_side_effect < 0:
        return False
    for item in history[last_side_effect:]:
        if item.get("has_observation"):
            return True
    return False


def _action_conclusion(name: str, text: str) -> str:
    """生成可存入胶囊的工具结论，排除 OCR 和键盘输入正文。"""
    if name == "keyboard_type":
        return "已执行键盘输入"
    if name in {"ocr", "ocr_locate"}:
        return "已完成文字识别"
    return text[:400]


def _tool_arguments(arguments: Any) -> dict[str, Any]:
    """解析工具参数供事实生命周期判断；坏参数只视为空对象。"""
    if isinstance(arguments, dict):
        return dict(arguments)
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _active_frame_path() -> str | None:
    """返回当前活动截图的稳定路径；没有有效帧时返回空。"""
    frame = active_view_frame()
    return str(frame.image_path) if frame is not None else None


def _target_label_for_move(
    context: TaskContext, name: str, arguments: dict[str, Any], frame_path: str | None
) -> str | None:
    """在移动前按当前帧事实取得定位标签，避免后置截图后读取陈旧编号。"""
    if name != "mouse_move" or arguments.get("target_id") is None:
        return None
    try:
        return locate_label(context, target_id=int(arguments["target_id"]), source_path=frame_path)
    except (TypeError, ValueError):
        return None


def _update_grounded_facts_after_tool(
    context: TaskContext,
    *,
    name: str,
    arguments: dict[str, Any],
    text: str,
    error: str | None,
    image_path: str | None,
    frame_before: str | None,
    target_label: str | None,
) -> TaskContext:
    """按工具语义维护短期事实，且不让后置截图复活旧定位坐标。"""
    if error:
        return clear_grounded_facts(context)
    if name == "locate":
        return _record_locate_facts(context, text=text, frame_path=frame_before)
    if name == "mouse_move":
        if target_label and image_path:
            return record_cursor_verification(context, label=target_label, source_path=image_path)
        return clear_grounded_facts(context)
    if name == "screenshot" and image_path:
        return clear_grounded_facts(context)
    if name in {"mouse_click", "mouse_drag", "mouse_scroll", "keyboard_type", "keyboard_press"}:
        return clear_grounded_facts(context)
    return context


def _record_locate_facts(context: TaskContext, *, text: str, frame_path: str | None) -> TaskContext:
    """只接受当前帧可执行 locate JSON，异常、空结果和观察专用输出都会失效旧事实。"""
    cleared = clear_grounded_facts(context, kinds={"locate"})
    if not frame_path:
        return cleared
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return cleared
    if not isinstance(payload, dict):
        return cleared
    if payload.get("coordinate_space") != "view" or payload.get("observation_only") is not False:
        return cleared
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return cleared
    items: list[tuple[int, str]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        try:
            target_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        label = str(item.get("label") or "").strip()
        if target_id > 0 and label:
            items.append((target_id, label))
    if not items:
        return cleared
    return replace_locate_facts(cleared, items=items, source_path=frame_path)


def _route_after_think(state: AgentState) -> Literal["think", "act", "__end__"]:
    """Think 之后：工具调用去 Act，缺完成声明时重试，其余结束。"""
    if state.get("status") == "acting":
        return "act"
    if state.get("status") == "thinking":
        return "think"
    return END


def _route_after_observe(state: AgentState) -> Literal["think", "__end__"]:
    """Observe 之后：完成门通过则结束，否则继续 Think。"""
    if state.get("status") in {"done", "error", "interrupted"}:
        return END
    return "think"


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
    if str(item.get("name") or payload.get("name") or "") == "locate":
        text = str(payload.get("text") or "")
        try:
            locate_payload = json.loads(text)
        except json.JSONDecodeError:
            locate_payload = None
        if isinstance(locate_payload, dict) and isinstance(locate_payload.get("items"), list):
            payload["text"] = json.dumps(
                {
                    "observation_ref": locate_payload.get("path")
                    or locate_payload.get("image_path"),
                    "candidate_count": len(locate_payload["items"]),
                    "summary": "已生成当前帧定位候选；详细框数据仅保留在观察图中。",
                },
                ensure_ascii=False,
            )
    return SessionMessage(role=str(item.get("role") or "assistant"), content=payload)
