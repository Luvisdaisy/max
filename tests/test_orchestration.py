"""验证编排状态图只调用已注册工具并在异常状态安全停止。"""

import unittest

from pydantic import BaseModel, ConfigDict

from max_agent.orchestration.graph import AgentOrchestrator
from max_agent.orchestration.models import OrchestrationRequest, TaskStatus
from max_agent.orchestration.prompts import build_planning_prompt
from max_agent.tools.base import ToolFailureCode, ToolReceipt
from max_agent.tools.registry import ToolRegistry


class _Payload(BaseModel):
    model_config = ConfigDict(extra="allow")


class _Tool:
    input_model = _Payload

    def __init__(self, name: str, receipts: list[ToolReceipt]) -> None:
        self.name = name
        self._receipts = receipts
        self.payloads: list[dict[str, object]] = []

    def invoke(self, tool_input: _Payload) -> ToolReceipt:
        self.payloads.append(tool_input.model_dump())
        return self._receipts.pop(0)


def _receipt(name: str, **data: object) -> ToolReceipt:
    return ToolReceipt(tool_name=name, success=True, data=data)


def _orchestrator(
    verify_receipts: list[ToolReceipt] | None = None,
    plan_receipts: list[ToolReceipt] | None = None,
) -> tuple[AgentOrchestrator, dict[str, _Tool]]:
    registry = ToolRegistry()
    tools = {
        "observe": _Tool(
            "observe", [_receipt("observe", fingerprint="same") for _ in range(4)]
        ),
        "plan": _Tool(
            "plan",
            plan_receipts
            or [_receipt("plan", action="click", text="secret") for _ in range(4)],
        ),
        "guard": _Tool("guard", [_receipt("guard") for _ in range(4)]),
        "act": _Tool("act", [_receipt("act") for _ in range(4)]),
        "verify": _Tool(
            "verify",
            verify_receipts or [_receipt("verify", completed=True, evidence=["done"])],
        ),
        "recover": _Tool("recover", [_receipt("recover") for _ in range(4)]),
    }
    for tool in tools.values():
        registry.register(tool)
    return AgentOrchestrator(registry, {name: name for name in tools}), tools


class OrchestrationTests(unittest.TestCase):
    def test_successful_graph_uses_only_registered_tools_and_redacts_text(self) -> None:
        orchestrator, tools = _orchestrator()

        result = orchestrator.run(OrchestrationRequest(user_goal="open settings"))

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(result.step_index, 1)
        self.assertEqual(result.verification_evidence, ["done"])
        self.assertNotIn("text", result.receipts[1].data)
        self.assertEqual(len(tools["guard"].payloads), 1)

    def test_tool_failure_stops_before_guard(self) -> None:
        failed_plan = ToolReceipt.failure(
            "plan", ToolFailureCode.UNAVAILABLE, "offline"
        )
        orchestrator, tools = _orchestrator(plan_receipts=[failed_plan])

        result = orchestrator.run(OrchestrationRequest(user_goal="open settings"))

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.reason, ToolFailureCode.UNAVAILABLE)
        self.assertEqual(tools["guard"].payloads, [])

    def test_cancelled_request_never_calls_tools(self) -> None:
        orchestrator, tools = _orchestrator()

        result = orchestrator.run(
            OrchestrationRequest(user_goal="stop", cancelled=True)
        )

        self.assertEqual(result.status, TaskStatus.ABORTED)
        self.assertEqual(tools["observe"].payloads, [])

    def test_call_user_waits_without_execution(self) -> None:
        orchestrator, tools = _orchestrator(
            plan_receipts=[_receipt("plan", action="call_user")]
        )

        result = orchestrator.run(OrchestrationRequest(user_goal="log in"))

        self.assertEqual(result.status, TaskStatus.WAITING_USER)
        self.assertEqual(tools["guard"].payloads, [])
        self.assertEqual(tools["act"].payloads, [])

    def test_three_no_progress_results_wait_for_user(self) -> None:
        incomplete = [_receipt("verify", completed=False) for _ in range(3)]
        orchestrator, tools = _orchestrator(verify_receipts=incomplete)

        result = orchestrator.run(OrchestrationRequest(user_goal="retry"))

        self.assertEqual(result.status, TaskStatus.WAITING_USER)
        self.assertEqual(result.reasoning_mode, "deliberate")
        self.assertEqual(len(tools["act"].payloads), 3)

    def test_prompt_contains_mode_and_goal_without_model_call(self) -> None:
        prompt = build_planning_prompt()

        messages = prompt.format_messages(
            user_goal="open settings",
            reasoning_mode="deliberate",
            observation="menu",
            history="none",
        )

        self.assertIn("deliberate", messages[1].content)
        self.assertIn("open settings", messages[1].content)


if __name__ == "__main__":
    unittest.main()
