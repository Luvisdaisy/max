"""以有向状态图编排已注册工具，推进请求并记录可审计步骤。"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from max_agent.orchestration.models import (
    OrchestrationRequest,
    OrchestrationResult,
    StepRecord,
    TaskStatus,
    ToolReceiptSummary,
    summarize_data,
)
from max_agent.tools.registry import ToolRegistry


class RuntimeState(TypedDict, total=False):
    """图节点之间传递的内部状态；不作为外部 API 暴露。"""

    task_id: str
    user_goal: str
    max_steps: int
    step_index: int
    status: str
    reason: str | None
    reasoning_mode: str
    no_progress_count: int
    cancelled: bool
    observation: dict[str, Any]
    receipts: list[ToolReceiptSummary]
    history: list[StepRecord]
    verification_evidence: list[str]


class AgentOrchestrator:
    """只通过工具注册表执行任务状态机的编排器。"""

    def __init__(self, registry: ToolRegistry, tool_names: dict[str, str]) -> None:
        self._registry = registry
        self._tool_names = tool_names
        self._graph = self._build_graph()

    def run(self, request: OrchestrationRequest) -> OrchestrationResult:
        """执行请求直到完成、失败、取消或需要用户继续为止。"""
        state = self._graph.invoke(
            RuntimeState(
                task_id=request.task_id,
                user_goal=request.user_goal,
                max_steps=request.max_steps,
                step_index=0,
                status=TaskStatus.INIT,
                reasoning_mode="fast",
                no_progress_count=0,
                cancelled=request.cancelled,
                receipts=[],
                history=[],
                verification_evidence=[],
            )
        )
        return OrchestrationResult(
            task_id=state["task_id"],
            status=TaskStatus(state["status"]),
            step_index=state["step_index"],
            reason=state.get("reason"),
            reasoning_mode=state["reasoning_mode"],
            receipts=state["receipts"],
            history=state["history"],
            verification_evidence=state["verification_evidence"],
        )

    def _build_graph(self):
        graph = StateGraph(RuntimeState)
        graph.add_node("observe", self._node("observe", TaskStatus.OBSERVING))
        graph.add_node("plan", self._node("plan", TaskStatus.PLANNING))
        graph.add_node("guard", self._node("guard", TaskStatus.GUARDING))
        graph.add_node("act", self._act)
        graph.add_node("verify", self._verify)
        graph.add_node("recover", self._recover)
        graph.add_node("succeeded", lambda state: {"status": TaskStatus.SUCCEEDED})
        graph.add_node("failed", lambda state: {"status": TaskStatus.FAILED})
        graph.add_node(
            "waiting_user", lambda state: {"status": TaskStatus.WAITING_USER}
        )
        graph.add_node("aborted", lambda state: {"status": TaskStatus.ABORTED})
        graph.add_edge(START, "observe")
        graph.add_conditional_edges(
            "observe", self._next_after_tool, self._tool_routes("plan")
        )
        graph.add_conditional_edges("plan", self._next_after_plan, self._plan_routes())
        graph.add_conditional_edges(
            "guard", self._next_after_guard, self._guard_routes()
        )
        graph.add_conditional_edges(
            "act", self._next_after_tool, self._tool_routes("verify")
        )
        graph.add_conditional_edges(
            "verify", self._next_after_verify, self._verify_routes()
        )
        graph.add_conditional_edges(
            "recover", self._next_after_recover, self._recover_routes()
        )
        for terminal in ("succeeded", "failed", "waiting_user", "aborted"):
            graph.add_edge(terminal, END)
        return graph.compile()

    def _tool_routes(self, success: str) -> dict[str, str]:
        return {"success": success, "failed": "failed", "aborted": "aborted"}

    def _plan_routes(self) -> dict[str, str]:
        return {
            "guard": "guard",
            "waiting_user": "waiting_user",
            "failed": "failed",
            "aborted": "aborted",
        }

    def _guard_routes(self) -> dict[str, str]:
        return {
            "act": "act",
            "waiting_user": "waiting_user",
            "failed": "failed",
            "aborted": "aborted",
        }

    def _verify_routes(self) -> dict[str, str]:
        return {
            "succeeded": "succeeded",
            "recover": "recover",
            "failed": "failed",
            "aborted": "aborted",
        }

    def _recover_routes(self) -> dict[str, str]:
        return {
            "observe": "observe",
            "plan": "plan",
            "waiting_user": "waiting_user",
            "failed": "failed",
            "aborted": "aborted",
        }

    def _node(self, phase: str, status: TaskStatus):
        def invoke(state: RuntimeState) -> dict[str, Any]:
            if state["cancelled"]:
                return {"status": TaskStatus.ABORTED, "reason": "cancelled"}
            return self._call_tool(phase, status, state)

        return invoke

    def _act(self, state: RuntimeState) -> dict[str, Any]:
        if state["cancelled"]:
            return {"status": TaskStatus.ABORTED, "reason": "cancelled"}
        if state["step_index"] >= state["max_steps"]:
            return {"status": TaskStatus.FAILED, "reason": "step_budget_exhausted"}
        update = self._call_tool("act", TaskStatus.ACTING, state)
        return {**update, "step_index": state["step_index"] + 1}

    def _verify(self, state: RuntimeState) -> dict[str, Any]:
        update = self._call_tool("verify", TaskStatus.VERIFYING, state)
        receipt = update["receipts"][-1]
        evidence = receipt.data.get("evidence", []) if receipt.success else []
        return {
            **update,
            "verification_evidence": state["verification_evidence"] + evidence,
        }

    def _recover(self, state: RuntimeState) -> dict[str, Any]:
        update = self._call_tool("recover", TaskStatus.RECOVERING, state)
        no_progress_count = state["no_progress_count"] + 1
        return {
            **update,
            "no_progress_count": no_progress_count,
            "reasoning_mode": "deliberate"
            if no_progress_count == 2
            else state["reasoning_mode"],
        }

    def _call_tool(
        self, phase: str, status: TaskStatus, state: RuntimeState
    ) -> dict[str, Any]:
        name = self._tool_names.get(phase)
        if name is None:
            return {
                "status": TaskStatus.FAILED,
                "reason": f"missing_tool_mapping:{phase}",
            }
        receipt = self._registry.invoke(
            name,
            {
                "goal": state["user_goal"],
                "reasoning_mode": state["reasoning_mode"],
                "observation": state.get("observation", {}),
            },
        )
        summary = ToolReceiptSummary(
            tool_name=receipt.tool_name,
            success=receipt.success,
            error_code=receipt.error.code if receipt.error else None,
            message=receipt.error.message if receipt.error else None,
            data=summarize_data(receipt.data),
        )
        update: dict[str, Any] = {
            "status": status,
            "receipts": state["receipts"] + [summary],
            "history": state["history"] + [StepRecord(phase=phase, receipt=summary)],
        }
        if not receipt.success:
            update["reason"] = summary.error_code or "tool_failed"
        if phase == "observe" and receipt.success:
            update["observation"] = summary.data
        return update

    def _next_after_tool(
        self, state: RuntimeState
    ) -> Literal["success", "failed", "aborted"]:
        if state["status"] == TaskStatus.ABORTED:
            return "aborted"
        return "success" if state["receipts"][-1].success else "failed"

    def _next_after_plan(
        self, state: RuntimeState
    ) -> Literal["guard", "waiting_user", "failed", "aborted"]:
        if state["status"] == TaskStatus.ABORTED:
            return "aborted"
        if not state["receipts"][-1].success:
            return "failed"
        if state["receipts"][-1].data.get("action") == "call_user":
            return "waiting_user"
        return "guard"

    def _next_after_guard(
        self, state: RuntimeState
    ) -> Literal["act", "waiting_user", "failed", "aborted"]:
        if state["status"] == TaskStatus.ABORTED:
            return "aborted"
        if not state["receipts"][-1].success:
            return "failed"
        return (
            "waiting_user"
            if state["receipts"][-1].data.get("requires_confirmation")
            else "act"
        )

    def _next_after_verify(
        self, state: RuntimeState
    ) -> Literal["succeeded", "recover", "failed", "aborted"]:
        if state["status"] == TaskStatus.ABORTED:
            return "aborted"
        receipt = state["receipts"][-1]
        if not receipt.success:
            return "failed"
        if receipt.data.get("completed"):
            return "succeeded"
        return "failed" if state["step_index"] >= state["max_steps"] else "recover"

    def _next_after_recover(
        self, state: RuntimeState
    ) -> Literal["observe", "plan", "waiting_user", "failed", "aborted"]:
        if state["status"] == TaskStatus.ABORTED:
            return "aborted"
        if not state["receipts"][-1].success:
            return "failed"
        if state["no_progress_count"] >= 3:
            return "waiting_user"
        if state["no_progress_count"] == 2:
            return "plan"
        return "observe"
