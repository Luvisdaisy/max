"""用 LangGraph 实现受预算、工具门和 Guard 约束的 text-or-tool 循环。"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from max_agent.orchestration.models import (
    AgentMessage,
    AgentRequest,
    AgentResult,
    ApprovedAction,
    BudgetLimits,
    BudgetUsage,
    CancellationToken,
    DesktopAction,
    FinalTextResponse,
    MessageRole,
    RuntimeEvent,
    StandardObservation,
    StepRecord,
    SuspendedTask,
    TaskStatus,
    ToolReceiptSummary,
    ToolUseResponse,
    WindowIdentity,
    action_hash,
    summarize_data,
)
from max_agent.orchestration.observation import (
    ObservationError,
    ObservationService,
    observation_fingerprint,
)
from max_agent.orchestration.resources import InMemoryResourceStore, ResourceRef
from max_agent.orchestration.session import (
    DesktopSessionBusy,
    DesktopSessionLock,
    InputStateCleaner,
)
from max_agent.tools.base import ToolContext, ToolFailureCode, ToolPhase, ToolReceipt
from max_agent.tools.registry import ToolRegistry

EventSink = Any


@dataclass(slots=True)
class _RunContext:
    task_id: str
    limits: BudgetLimits
    usage: BudgetUsage
    resources: InMemoryResourceStore
    cancellation: CancellationToken
    emit: EventSink | None
    started_at: float

    def consume(self, bucket: str) -> bool:
        if (
            self.cancellation.cancelled
            or time.monotonic() - self.started_at >= self.limits.total_timeout_seconds
        ):
            return False
        current = int(getattr(self.usage, bucket))
        limit = int(getattr(self.limits, bucket))
        if current >= limit:
            return False
        setattr(self.usage, bucket, current + 1)
        return True

    def tool_context(self, phase: ToolPhase) -> ToolContext:
        return ToolContext(
            task_id=self.task_id,
            phase=phase,
            resources=self.resources,
            cancellation=self.cancellation,
            consume_budget=self.consume,
            emit=self.emit,
        )

    def event(
        self,
        phase: str,
        state: Literal["running", "succeeded", "failed"],
        *,
        tool_name: str | None = None,
        elapsed_seconds: float = 0.0,
        message: str | None = None,
    ) -> None:
        if self.emit is not None:
            self.emit(
                RuntimeEvent(
                    phase=phase,
                    state=state,
                    tool_name=tool_name,
                    elapsed_seconds=elapsed_seconds,
                    message=message,
                )
            )


class RuntimeState(TypedDict, total=False):
    task_id: str
    user_goal: str
    messages: list[AgentMessage]
    status: TaskStatus
    reason: str | None
    response_text: str
    current_response: FinalTextResponse | ToolUseResponse
    current_call: ToolUseResponse
    pending_receipt: ToolReceipt
    approved: ApprovedAction
    action: DesktopAction
    observation_parts: dict[str, Any]
    observation: StandardObservation
    before_observation: StandardObservation
    side_effect_used: bool
    latest_verified: bool
    no_progress_count: int
    repeated_call_count: int
    last_call_signature: str | None
    reasoning_mode: str
    receipts: list[ToolReceiptSummary]
    history: list[StepRecord]
    verification_evidence: list[str]
    question: str
    confirmation_hash: str | None
    context: _RunContext


class AgentRuntime:
    """拥有消息循环、挂起任务、桌面锁、清理和脱敏归档的运行时。"""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        resources: InMemoryResourceStore | None = None,
        session_lock: DesktopSessionLock | None = None,
        cleaner: InputStateCleaner | None = None,
        reset_model: Any | None = None,
    ) -> None:
        self.registry = registry
        self.resources = resources or InMemoryResourceStore()
        self.session_lock = session_lock or DesktopSessionLock()
        self.cleaner = cleaner or InputStateCleaner()
        self._reset_model = reset_model
        self._observation_service = ObservationService(registry)
        self._graph = self._build_graph()
        self._suspended: SuspendedTask | None = None
        self._active_token: CancellationToken | None = None

    @property
    def suspended_task_id(self) -> str | None:
        return self._suspended.task_id if self._suspended else None

    def run(self, request: AgentRequest, emit: EventSink | None = None) -> AgentResult:
        """运行新任务；存在挂起任务时把新消息视为恢复输入。"""
        if self._suspended is not None:
            return self.resume(request.user_goal, emit)
        return self._run(
            task_id=request.task_id,
            user_goal=request.user_goal,
            messages=[AgentMessage(role=MessageRole.USER, content=request.user_goal)],
            limits=request.budgets,
            usage=BudgetUsage(),
            reasoning_mode="fast",
            cancelled=request.cancelled,
            confirmation_hash=None,
            emit=emit,
        )

    def resume(self, user_message: str, emit: EventSink | None = None) -> AgentResult:
        """恢复挂起任务；旧图像、坐标和批准已在挂起时释放。"""
        suspended = self._suspended
        if suspended is None:
            raise RuntimeError("no suspended task")
        self._suspended = None
        return self._run(
            task_id=suspended.task_id,
            user_goal=suspended.user_goal_summary,
            messages=[
                *suspended.messages,
                AgentMessage(role=MessageRole.USER, content=user_message),
            ],
            limits=suspended.budgets,
            usage=suspended.usage,
            reasoning_mode=suspended.reasoning_mode,
            cancelled=False,
            confirmation_hash=suspended.confirmed_action_hash,
            emit=emit,
        )

    def cancel(self) -> None:
        if self._active_token is not None:
            self._active_token.cancel()

    def clear(self) -> None:
        """取消活动任务、丢弃挂起状态并重置独立 Agent 模型会话。"""
        self.cancel()
        if self._suspended is not None:
            self.resources.clear_task(self._suspended.task_id)
        self._suspended = None
        if self._reset_model is not None:
            self._reset_model()

    def _run(
        self,
        *,
        task_id: str,
        user_goal: str,
        messages: list[AgentMessage],
        limits: BudgetLimits,
        usage: BudgetUsage,
        reasoning_mode: str,
        cancelled: bool,
        confirmation_hash: str | None,
        emit: EventSink | None,
    ) -> AgentResult:
        token = CancellationToken(cancelled)
        self._active_token = token
        context = _RunContext(
            task_id, limits, usage, self.resources, token, emit, time.monotonic()
        )
        state = RuntimeState(
            task_id=task_id,
            user_goal=user_goal,
            messages=messages,
            status=TaskStatus.INIT,
            response_text="",
            observation_parts={},
            side_effect_used=False,
            latest_verified=False,
            no_progress_count=0,
            repeated_call_count=0,
            last_call_signature=None,
            reasoning_mode=reasoning_mode,
            receipts=[],
            history=[],
            verification_evidence=[],
            confirmation_hash=confirmation_hash,
            context=context,
        )
        cleanup_errors: list[str] = []
        try:
            state = self._graph.invoke(state, config={"recursion_limit": 256})
        except Exception as error:
            state["status"] = TaskStatus.FAILED
            state["reason"] = f"RUNTIME_ERROR:{type(error).__name__}"
            state["response_text"] = "Agent 运行失败，桌面输入已停止。"
        finally:
            # 纯问答和只读工具从未持有输入状态，不能为了“清理”而发送 keyUp/mouseUp。
            if state.get("side_effect_used", False):
                cleanup_errors.extend(self.cleaner.cleanup())
            self.resources.clear_task(task_id)
            self.session_lock.release(task_id)
            self._active_token = None
        if state["status"] == TaskStatus.WAITING_USER:
            self._suspended = SuspendedTask(
                task_id=task_id,
                user_goal_summary=_suspended_goal_summary(user_goal),
                messages=_minimal_messages(state["messages"]),
                question="需要用户继续处理。",
                budgets=limits,
                usage=usage,
                reasoning_mode="deliberate"
                if state["reasoning_mode"] == "deliberate"
                else "fast",
                confirmed_action_hash=state.get("confirmation_hash"),
            )
        result = AgentResult(
            task_id=task_id,
            status=state["status"],
            response_text=state.get("response_text")
            or _default_response(state["status"], state.get("reason")),
            reason=state.get("reason"),
            usage=usage,
            receipts=state["receipts"],
            history=state["history"],
            verification_evidence=state["verification_evidence"],
            resume_token=task_id
            if state["status"] == TaskStatus.WAITING_USER
            else None,
            cleanup_errors=cleanup_errors,
        )
        self._archive(result)
        return result

    def _archive(self, result: AgentResult) -> None:
        tool = self.registry.get("archive_run")
        if tool is None or result.status == TaskStatus.WAITING_USER:
            return
        usage = result.usage
        context = _RunContext(
            result.task_id,
            BudgetLimits(tool_calls=1),
            BudgetUsage(),
            self.resources,
            CancellationToken(),
            None,
            time.monotonic(),
        )
        self.registry.invoke(
            "archive_run",
            {
                "task_id": result.task_id,
                "status": result.status,
                "config": {"budgets": usage.model_dump()},
                "trajectory": [item.model_dump() for item in result.history],
                "result": {
                    **result.model_dump(exclude={"response_text"}),
                    "response_sha256": hashlib.sha256(
                        result.response_text.encode()
                    ).hexdigest(),
                    "response_length": len(result.response_text),
                },
            },
            context.tool_context(ToolPhase.ARCHIVE),
        )

    def _build_graph(self):
        graph = StateGraph(RuntimeState)
        graph.add_node("reason", self._reason)
        graph.add_node("tool_gate", self._tool_gate)
        graph.add_node("execute_read_only", self._execute_read_only)
        graph.add_node("guard", self._guard)
        graph.add_node("act", self._act)
        graph.add_node("observe_after_action", self._observe_after_action)
        graph.add_node("verify", self._verify)
        graph.add_node("recover", self._recover)
        graph.add_node("append_result", self._append_result)
        graph.add_node("succeeded", lambda state: {"status": TaskStatus.SUCCEEDED})
        graph.add_node(
            "waiting_user", lambda state: {"status": TaskStatus.WAITING_USER}
        )
        graph.add_node("failed", lambda state: {"status": TaskStatus.FAILED})
        graph.add_node("aborted", lambda state: {"status": TaskStatus.ABORTED})
        graph.add_edge(START, "reason")
        graph.add_conditional_edges("reason", self._route_reason)
        graph.add_conditional_edges("tool_gate", self._route_tool_gate)
        graph.add_edge("execute_read_only", "append_result")
        graph.add_conditional_edges("guard", self._route_guard)
        graph.add_conditional_edges("act", self._route_act)
        graph.add_conditional_edges("observe_after_action", self._route_observation)
        graph.add_conditional_edges("verify", self._route_verify)
        graph.add_conditional_edges("recover", self._route_recover)
        graph.add_conditional_edges("append_result", self._route_append)
        for terminal in ("succeeded", "waiting_user", "failed", "aborted"):
            graph.add_edge(terminal, END)
        return graph.compile()

    def _reason(self, state: RuntimeState) -> dict[str, Any]:
        context = state["context"]
        if context.cancellation.cancelled:
            return {"status": TaskStatus.ABORTED, "reason": "cancelled"}
        context.event("reason", "running", tool_name="invoke_model")
        started = time.monotonic()
        image_refs = []
        observation = state.get("observation")
        if observation is not None and observation.image_ref is not None:
            image_refs.append(
                ResourceRef.model_validate(observation.image_ref).model_dump()
            )
        receipt = self.registry.invoke(
            "invoke_model",
            {
                "messages": [message.model_dump() for message in state["messages"]],
                "tools": list(self.registry.model_tools()),
                "reasoning_mode": state["reasoning_mode"],
                "image_refs": image_refs,
            },
            context.tool_context(ToolPhase.REASON),
        )
        context.event(
            "reason",
            "succeeded" if receipt.success else "failed",
            tool_name="invoke_model",
            elapsed_seconds=time.monotonic() - started,
        )
        audit = _summary(receipt)
        update: dict[str, Any] = {
            "receipts": [*state["receipts"], audit],
            "history": [*state["history"], StepRecord(phase="reason", receipt=audit)],
            "status": TaskStatus.REASONING,
        }
        if not receipt.success:
            update.update(
                status=TaskStatus.FAILED,
                reason=receipt.error.message if receipt.error else "MODEL_FAILED",
                response_text="本地模型无法继续当前任务。",
            )
            return update
        payload = receipt.data["response"]
        response = (
            FinalTextResponse.model_validate(payload)
            if payload.get("type") == "text"
            else ToolUseResponse.model_validate(payload)
        )
        if (
            isinstance(response, FinalTextResponse)
            and state["side_effect_used"]
            and not state["latest_verified"]
        ):
            failure = ToolReceipt.failure(
                "goal_verification", ToolFailureCode.POLICY_DENIED, "GOAL_NOT_VERIFIED"
            )
            return {
                **update,
                "pending_receipt": failure,
                "current_response": response,
                "status": TaskStatus.APPENDING_RESULT,
            }
        if isinstance(response, FinalTextResponse):
            update.update(current_response=response, response_text=response.text)
        else:
            update.update(current_response=response, current_call=response)
        return update

    def _route_reason(self, state: RuntimeState) -> str:
        if state["status"] == TaskStatus.ABORTED:
            return "aborted"
        if state["status"] == TaskStatus.FAILED:
            return "failed"
        if state["status"] == TaskStatus.APPENDING_RESULT:
            return "append_result"
        return (
            "succeeded"
            if isinstance(state["current_response"], FinalTextResponse)
            else "tool_gate"
        )

    def _tool_gate(self, state: RuntimeState) -> dict[str, Any]:
        call = state["current_call"]
        tool = self.registry.get(call.tool_name)
        messages = [
            *state["messages"],
            AgentMessage(
                role=MessageRole.ASSISTANT,
                content={
                    "type": "tool_use",
                    "tool_name": call.tool_name,
                    "arguments": call.arguments,
                },
                tool_name=call.tool_name,
                tool_call_id=call.call_id,
            ),
        ]
        # 循环检测使用内存中的完整参数摘要；只保留不可逆哈希，既区分不同输入又不泄露文本。
        signature_payload = json.dumps(
            [call.tool_name, call.arguments], sort_keys=True, ensure_ascii=False
        )
        signature = hashlib.sha256(signature_payload.encode()).hexdigest()
        repeated = (
            state["repeated_call_count"] + 1
            if signature == state.get("last_call_signature")
            else 0
        )
        update: dict[str, Any] = {
            "messages": messages,
            "status": TaskStatus.TOOL_GATE,
            "last_call_signature": signature,
            "repeated_call_count": repeated,
        }
        if repeated > state["context"].limits.repeated_calls:
            return {
                **update,
                "status": TaskStatus.WAITING_USER,
                "reason": "NO_PROGRESS",
                "question": "工具调用没有产生新进展，请确认目标或手动调整桌面后继续。",
                "response_text": "工具调用没有产生新进展，请确认目标或手动调整桌面后继续。",
            }
        if tool is None or not getattr(tool, "model_visible", False):
            return {
                **update,
                "pending_receipt": ToolReceipt.failure(
                    call.tool_name,
                    ToolFailureCode.PERMISSION_DENIED,
                    "tool is not exposed to the model",
                ),
                "status": TaskStatus.APPENDING_RESULT,
            }
        if call.tool_name == "request_user":
            receipt = self.registry.invoke(
                call.tool_name,
                call.arguments,
                state["context"].tool_context(ToolPhase.TOOL),
            )
            question = (
                str(receipt.data.get("question", "需要用户处理。"))
                if receipt.success
                else "需要用户处理。"
            )
            return {
                **update,
                "pending_receipt": receipt,
                "status": TaskStatus.WAITING_USER,
                "question": question,
                "response_text": question,
            }
        if getattr(tool, "side_effect", False):
            try:
                action = DesktopAction.model_validate(call.arguments)
            except Exception:
                return {
                    **update,
                    "pending_receipt": ToolReceipt.failure(
                        call.tool_name,
                        ToolFailureCode.INVALID_INPUT,
                        "invalid desktop action",
                    ),
                    "status": TaskStatus.APPENDING_RESULT,
                }
            return {**update, "action": action, "status": TaskStatus.GUARDING}
        return update

    def _route_tool_gate(self, state: RuntimeState) -> str:
        if state["status"] == TaskStatus.WAITING_USER:
            return "waiting_user"
        if state["status"] == TaskStatus.APPENDING_RESULT:
            return "append_result"
        if state["status"] == TaskStatus.GUARDING:
            return "guard"
        return "execute_read_only"

    def _execute_read_only(self, state: RuntimeState) -> dict[str, Any]:
        call = state["current_call"]
        context = state["context"]
        context.event("tool", "running", tool_name=call.tool_name)
        started = time.monotonic()
        receipt = self.registry.invoke(
            call.tool_name, call.arguments, context.tool_context(ToolPhase.TOOL)
        )
        context.event(
            "tool",
            "succeeded" if receipt.success else "failed",
            tool_name=call.tool_name,
            elapsed_seconds=time.monotonic() - started,
        )
        return {"pending_receipt": receipt, "status": TaskStatus.APPENDING_RESULT}

    def _guard(self, state: RuntimeState) -> dict[str, Any]:
        observation = state.get("observation")
        if observation is None:
            return {
                "pending_receipt": ToolReceipt.failure(
                    "desktop_action",
                    ToolFailureCode.STALE_TARGET,
                    "observe the desktop before proposing an action",
                ),
                "status": TaskStatus.APPENDING_RESULT,
            }
        try:
            self.session_lock.acquire(state["task_id"])
        except DesktopSessionBusy:
            return {
                "status": TaskStatus.FAILED,
                "reason": "SESSION_BUSY",
                "response_text": "桌面正由另一个任务控制。",
            }
        context = state["context"]
        context.event("guard", "running", tool_name="approve_action")
        started = time.monotonic()
        receipt = self.registry.invoke(
            "approve_action",
            {
                "action": state["action"].model_dump(),
                "observation": observation.model_dump(),
                "user_confirmed": state.get("confirmation_hash")
                == action_hash(state["action"]),
            },
            context.tool_context(ToolPhase.GUARD),
        )
        context.event(
            "guard",
            "succeeded" if receipt.success else "failed",
            tool_name="approve_action",
            elapsed_seconds=time.monotonic() - started,
        )
        if not receipt.success:
            return {"pending_receipt": receipt, "status": TaskStatus.APPENDING_RESULT}
        if receipt.data.get("requires_user"):
            question = str(receipt.data["question"])
            return {
                "status": TaskStatus.WAITING_USER,
                "question": question,
                "response_text": question,
                "confirmation_hash": receipt.data.get("action_hash"),
            }
        return {
            "approved": ApprovedAction.model_validate(receipt.data["approved"]),
            "confirmation_hash": None,
            "status": TaskStatus.ACTING,
        }

    def _route_guard(self, state: RuntimeState) -> str:
        if state["status"] == TaskStatus.WAITING_USER:
            return "waiting_user"
        if state["status"] == TaskStatus.FAILED:
            return "failed"
        if state["status"] == TaskStatus.APPENDING_RESULT:
            return "append_result"
        return "act"

    def _act(self, state: RuntimeState) -> dict[str, Any]:
        context = state["context"]
        context.event("action", "running", tool_name="execute_action")
        started = time.monotonic()
        receipt = self.registry.invoke(
            "execute_action",
            {
                "approved": state["approved"].model_dump(),
                "current_fingerprint": state["observation"].fingerprint,
            },
            context.tool_context(ToolPhase.ACTION),
        )
        context.event(
            "action",
            "succeeded" if receipt.success else "failed",
            tool_name="execute_action",
            elapsed_seconds=time.monotonic() - started,
        )
        return {
            "pending_receipt": receipt,
            "before_observation": state["observation"],
            "side_effect_used": True,
            "latest_verified": False,
            "status": TaskStatus.OBSERVING
            if receipt.success
            else TaskStatus.APPENDING_RESULT,
        }

    def _route_act(self, state: RuntimeState) -> str:
        return (
            "observe_after_action"
            if state["status"] == TaskStatus.OBSERVING
            else "append_result"
        )

    def _observe_after_action(self, state: RuntimeState) -> dict[str, Any]:
        context = state["context"]
        context.event("observe_after_action", "running", tool_name="observe_screen")
        started = time.monotonic()
        try:
            observation, receipts = self._observation_service.observe(
                context.tool_context(ToolPhase.OBSERVE_AFTER_ACTION),
                state.get("observation"),
            )
        except ObservationError as error:
            context.event(
                "observe_after_action",
                "failed",
                tool_name="observe_screen",
                elapsed_seconds=time.monotonic() - started,
            )
            return {
                "pending_receipt": ToolReceipt.failure(
                    "observe_after_action", ToolFailureCode.UNAVAILABLE, str(error)
                ),
                "status": TaskStatus.APPENDING_RESULT,
            }
        context.event(
            "observe_after_action",
            "succeeded",
            tool_name="observe_screen",
            elapsed_seconds=time.monotonic() - started,
        )
        audits = [_summary(receipt) for receipt in receipts]
        return {
            "observation": observation,
            "receipts": [*state["receipts"], *audits],
            "history": [
                *state["history"],
                *(
                    StepRecord(phase="observe_after_action", receipt=item)
                    for item in audits
                ),
            ],
            "status": TaskStatus.VERIFYING,
        }

    def _route_observation(self, state: RuntimeState) -> str:
        return "verify" if state["status"] == TaskStatus.VERIFYING else "append_result"

    def _verify(self, state: RuntimeState) -> dict[str, Any]:
        context = state["context"]
        context.event("verify", "running", tool_name="verify_result")
        started = time.monotonic()
        receipt = self.registry.invoke(
            "verify_result",
            {
                "user_goal": state["user_goal"],
                "action": state["action"].model_dump(),
                "before": state["before_observation"].model_dump(),
                "after": state["observation"].model_dump(),
            },
            context.tool_context(ToolPhase.VERIFY),
        )
        context.event(
            "verify",
            "succeeded" if receipt.success else "failed",
            tool_name="verify_result",
            elapsed_seconds=time.monotonic() - started,
        )
        completed = receipt.success and bool(receipt.data.get("completed"))
        evidence = list(receipt.data.get("evidence", [])) if receipt.success else []
        no_progress = (
            state["no_progress_count"] + 1 if receipt.data.get("no_progress") else 0
        )
        combined = ToolReceipt(
            tool_name=state["current_call"].tool_name,
            success=receipt.success,
            data={
                "executed": state["pending_receipt"].success,
                "verified": completed,
                "verification": summarize_data(receipt.data),
                "observation": _observation_for_model(state["observation"]),
            },
            error=receipt.error,
        )
        return {
            "pending_receipt": combined,
            "latest_verified": completed,
            "no_progress_count": no_progress,
            "verification_evidence": [*state["verification_evidence"], *evidence],
            "status": TaskStatus.APPENDING_RESULT
            if completed
            else TaskStatus.RECOVERING,
        }

    def _route_verify(self, state: RuntimeState) -> str:
        return (
            "append_result"
            if state["status"] == TaskStatus.APPENDING_RESULT
            else "recover"
        )

    def _recover(self, state: RuntimeState) -> dict[str, Any]:
        remaining = max(
            0, state["context"].limits.recoveries - state["context"].usage.recoveries
        )
        if not state["context"].consume("recoveries"):
            return {
                "status": TaskStatus.FAILED,
                "reason": "RECOVERY_BUDGET_EXHAUSTED",
                "response_text": "任务恢复预算已耗尽。",
            }
        context = state["context"]
        context.event("recover", "running", tool_name="recover")
        started = time.monotonic()
        receipt = self.registry.invoke(
            "recover",
            {
                "no_progress_count": state["no_progress_count"],
                "remaining_recoveries": remaining,
            },
            context.tool_context(ToolPhase.RECOVER),
        )
        context.event(
            "recover",
            "succeeded" if receipt.success else "failed",
            tool_name="recover",
            elapsed_seconds=time.monotonic() - started,
        )
        decision = receipt.data.get("decision") if receipt.success else "fail"
        if decision == "wait_user":
            question = "桌面状态连续没有进展，请手动调整后告诉我继续。"
            return {
                "status": TaskStatus.WAITING_USER,
                "question": question,
                "response_text": question,
                "reason": "NO_PROGRESS",
            }
        if decision == "fail":
            return {
                "status": TaskStatus.FAILED,
                "reason": "NO_PROGRESS",
                "response_text": "桌面任务没有取得可验证进展。",
            }
        return {
            "status": TaskStatus.APPENDING_RESULT,
            "reasoning_mode": "deliberate"
            if decision == "deliberate_reason"
            else state["reasoning_mode"],
        }

    def _route_recover(self, state: RuntimeState) -> str:
        if state["status"] == TaskStatus.WAITING_USER:
            return "waiting_user"
        if state["status"] == TaskStatus.FAILED:
            return "failed"
        return "append_result"

    def _append_result(self, state: RuntimeState) -> dict[str, Any]:
        receipt = state["pending_receipt"]
        call = state.get("current_call")
        call_id = call.call_id if call is not None else "runtime"
        messages = [
            *state["messages"],
            AgentMessage(
                role=MessageRole.TOOL,
                tool_name=receipt.tool_name,
                tool_call_id=call_id,
                content=_receipt_for_model(receipt),
            ),
        ]
        parts = dict(state["observation_parts"])
        if receipt.success:
            if receipt.tool_name == "observe_screen":
                parts["screen"] = receipt.data
            elif receipt.tool_name == "observe_windows":
                parts["windows"] = receipt.data.get("windows", [])
            elif receipt.tool_name == "recognize_text":
                parts["ocr_lines"] = receipt.data.get("lines", [])
        observation = _compose_observation(parts)
        audit = _summary(receipt)
        return {
            "messages": messages,
            "observation_parts": parts,
            "observation": observation or state.get("observation"),
            "receipts": [*state["receipts"], audit],
            "history": [
                *state["history"],
                StepRecord(
                    phase="tool_result",
                    receipt=audit,
                    # 模型摘要不参与授权，也不直接进入审计，避免模型回显敏感工具参数。
                    audit_summary="model_selected_tool"
                    if call is not None and call.audit_summary
                    else None,
                ),
            ],
            "status": TaskStatus.REASONING,
        }

    def _route_append(self, state: RuntimeState) -> str:
        if state["context"].cancellation.cancelled:
            return "aborted"
        return "reason"


# 旧名称保留为运行时入口别名，避免下游导入立即失效。
AgentOrchestrator = AgentRuntime


def _summary(receipt: ToolReceipt) -> ToolReceiptSummary:
    return ToolReceiptSummary(
        tool_name=receipt.tool_name,
        success=receipt.success,
        error_code=receipt.error.code if receipt.error else None,
        message=receipt.error.message if receipt.error else None,
        data=summarize_data(receipt.data),
    )


def _receipt_for_model(receipt: ToolReceipt) -> dict[str, Any]:
    if receipt.success:
        return {"success": True, "data": receipt.data}
    return {
        "success": False,
        "error": {
            "code": receipt.error.code if receipt.error else "tool_failed",
            "message": receipt.error.message if receipt.error else "tool failed",
        },
    }


def _compose_observation(parts: dict[str, Any]) -> StandardObservation | None:
    screen = parts.get("screen")
    if not screen:
        return None
    windows = list(parts.get("windows", []))
    ocr_lines = list(parts.get("ocr_lines", []))
    foreground_payload = screen.get("foreground_window")
    foreground = (
        WindowIdentity.model_validate(foreground_payload)
        if foreground_payload
        else None
    )
    fingerprint = observation_fingerprint(windows, ocr_lines, foreground)
    return StandardObservation(
        image_ref=ResourceRef.model_validate(screen["image_ref"]),
        captured_at=screen["captured_at"],
        bounds=screen["bounds"],
        dpi=screen.get("dpi"),
        foreground_window=foreground,
        windows=windows,
        ocr_lines=ocr_lines,
        fingerprint=fingerprint,
    )


def _observation_for_model(observation: StandardObservation) -> dict[str, Any]:
    return {
        "captured_at": observation.captured_at,
        "bounds": observation.bounds.model_dump(),
        "dpi": observation.dpi,
        "foreground_window": observation.foreground_window.model_dump()
        if observation.foreground_window
        else None,
        "windows": observation.windows,
        "ocr_lines": observation.ocr_lines,
        "fingerprint": observation.fingerprint,
    }


def _minimal_messages(messages: list[AgentMessage]) -> list[AgentMessage]:
    """挂起态只保留对话语义，不保留资源引用、坐标或工具原始结果。"""
    minimized: list[AgentMessage] = []
    for message in messages:
        content = message.content
        if message.role == MessageRole.USER:
            content = _suspended_goal_summary(str(content))
        elif message.role == MessageRole.ASSISTANT and isinstance(content, dict):
            raw = json.dumps(
                content.get("arguments", {}), ensure_ascii=False, sort_keys=True
            )
            content = {
                "type": content.get("type", "tool_use"),
                "tool_name": content.get("tool_name", message.tool_name),
                "arguments_hash": hashlib.sha256(raw.encode()).hexdigest(),
            }
        elif message.role == MessageRole.TOOL:
            content = {
                "tool_name": message.tool_name,
                "result_available_before_suspend": True,
            }
        minimized.append(message.model_copy(update={"content": content}))
    return minimized


def _suspended_goal_summary(_goal: str) -> str:
    """挂起态不保留原始目标文本；恢复后模型可重新询问缺失的敏感参数。"""
    return "继续先前用户任务；原始目标参数已在挂起时脱敏。"


def _default_response(status: TaskStatus, reason: str | None) -> str:
    if status == TaskStatus.ABORTED:
        return "任务已取消。"
    if status == TaskStatus.WAITING_USER:
        return "需要用户继续处理。"
    return f"任务未完成：{reason or 'unknown error'}"
