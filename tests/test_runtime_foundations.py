"""验证运行时契约、资源隔离、工具门与会话清理基础。"""

import json
import time
import unittest

from PIL import Image
from pydantic import BaseModel

from max_agent.orchestration.models import (
    BudgetLimits,
    CancellationToken,
    DesktopAction,
    FinalTextResponse,
    ToolUseResponse,
    summarize_data,
)
from max_agent.orchestration.resources import InMemoryResourceStore, ResourceError
from max_agent.orchestration.session import (
    DesktopSessionBusy,
    DesktopSessionLock,
    InputStateCleaner,
)
from max_agent.tools.base import (
    ToolContext,
    ToolFailureCode,
    ToolPermission,
    ToolPhase,
    ToolReceipt,
)
from max_agent.tools.registry import ToolRegistry


class _Input(BaseModel):
    value: int


class _Tool:
    name = "foundation_echo"
    description = "echo"
    input_model = _Input
    permission = ToolPermission.OBSERVE
    allowed_phases = frozenset({ToolPhase.TOOL})
    timeout_seconds = 1.0
    recoverable = True
    model_visible = True
    side_effect = False

    def invoke(
        self, tool_input: _Input, context: ToolContext | None = None
    ) -> ToolReceipt:
        return ToolReceipt(
            tool_name=self.name, success=True, data={"value": tool_input.value}
        )


class _SlowTool(_Tool):
    name = "slow"
    timeout_seconds = 0.01

    def invoke(
        self, tool_input: _Input, context: ToolContext | None = None
    ) -> ToolReceipt:
        time.sleep(0.03)
        return super().invoke(tool_input, context)


class RuntimeFoundationTests(unittest.TestCase):
    def test_model_response_and_action_contracts_reject_invalid_combinations(
        self,
    ) -> None:
        self.assertEqual(FinalTextResponse(text="完成").type, "text")
        self.assertEqual(ToolUseResponse(tool_name="observe_screen").type, "tool_use")
        with self.assertRaises(ValueError):
            DesktopAction(kind="click")
        with self.assertRaises(ValueError):
            DesktopAction(kind="wait", seconds=1, text="secret")

    def test_audit_projection_removes_sensitive_working_data(self) -> None:
        projected = summarize_data(
            {
                "image": Image.new("RGB", (1, 1)),
                "password": "p",
                "nested": {"text": "secret", "count": 2},
            }
        )
        self.assertEqual(projected, {"nested": {"count": 2}})
        self.assertNotIn("secret", json.dumps(projected))

    def test_audit_projection_reduces_desktop_observation_to_counts(self) -> None:
        projected = summarize_data(
            {
                "windows": [
                    {
                        "title": "private document title",
                        "executable_path": "C:/Windows/notepad.exe",
                    }
                ],
                "ocr_lines": [{"text": "private OCR text"}],
                "lines": [{"text": "another private OCR text"}],
                "image_ref": {"id": "unguessable-resource-id"},
                "foreground_window": {"title": "private foreground title"},
                "response": {
                    "type": "tool_use",
                    "tool_name": "desktop_action",
                    "arguments": {"text": "private input"},
                },
            }
        )

        self.assertEqual(
            projected,
            {
                "window_count": 1,
                "ocr_line_count": 1,
                "image_ref_present": True,
                "foreground_window_present": True,
                "response": {"type": "tool_use", "tool_name": "desktop_action"},
            },
        )
        self.assertNotIn("private", json.dumps(projected))

    def test_resource_store_enforces_task_and_type_and_release(self) -> None:
        store = InMemoryResourceStore()
        image = Image.new("RGB", (2, 2))
        ref = store.put("task-a", "image", image)
        self.assertIs(store.get(ref, "task-a", "image"), image)
        with self.assertRaises(ResourceError):
            store.get(ref, "task-b", "image")
        with self.assertRaises(ResourceError):
            store.get(ref, "task-a", "template")
        store.clear_task("task-a")
        with self.assertRaises(ResourceError):
            store.get(ref, "task-a")

    def test_registry_checks_phase_budget_cancel_and_input(self) -> None:
        registry = ToolRegistry()
        registry.register(_Tool())
        store = InMemoryResourceStore()
        remaining = {"value": 1}

        def consume(_bucket: str) -> bool:
            if remaining["value"] == 0:
                return False
            remaining["value"] -= 1
            return True

        context = ToolContext(
            "task", ToolPhase.TOOL, store, CancellationToken(), consume
        )
        self.assertTrue(
            registry.invoke("foundation_echo", {"value": 1}, context).success
        )
        self.assertEqual(
            registry.invoke("foundation_echo", {"value": 2}, context).error.code,
            ToolFailureCode.BUDGET_EXHAUSTED,
        )
        denied = ToolContext(
            "task", ToolPhase.GUARD, store, CancellationToken(), lambda _: True
        )
        self.assertEqual(
            registry.invoke("foundation_echo", {"value": 1}, denied).error.code,
            ToolFailureCode.PHASE_DENIED,
        )
        cancelled = CancellationToken(True)
        cancelled_context = ToolContext(
            "task", ToolPhase.TOOL, store, cancelled, lambda _: True
        )
        self.assertEqual(
            registry.invoke(
                "foundation_echo", {"value": 1}, cancelled_context
            ).error.code,
            ToolFailureCode.CANCELLED,
        )
        strict_context = ToolContext(
            "task", ToolPhase.TOOL, store, CancellationToken(), lambda _: True
        )
        unknown = registry.invoke(
            "foundation_echo",
            {"value": 1, "unexpected": "ignored-before"},
            strict_context,
        )
        self.assertEqual(unknown.error.code, ToolFailureCode.INVALID_INPUT)

    def test_desktop_lock_and_cleaner_are_safe_on_repeated_or_partial_failure(
        self,
    ) -> None:
        lock = DesktopSessionLock()
        lock.acquire("one")
        lock.acquire("one")
        with self.assertRaises(DesktopSessionBusy):
            lock.acquire("two")
        lock.release("other")
        lock.release("one")
        lock.release("one")
        called: list[str] = []

        def fail() -> None:
            called.append("fail")
            raise RuntimeError("release failed")

        cleaner = InputStateCleaner((fail, lambda: called.append("done")))
        self.assertEqual(len(cleaner.cleanup()), 1)
        self.assertEqual(called, ["fail", "done"])

    def test_budget_contract_has_independent_hard_limits(self) -> None:
        limits = BudgetLimits(model_turns=2, tool_calls=3, actions=1, recoveries=1)
        self.assertEqual(
            (limits.model_turns, limits.tool_calls, limits.actions), (2, 3, 1)
        )

    def test_registry_timeout_returns_stable_failure_without_guessing_result(
        self,
    ) -> None:
        registry = ToolRegistry()
        registry.register(_SlowTool())
        context = ToolContext(
            "task",
            ToolPhase.TOOL,
            InMemoryResourceStore(),
            CancellationToken(),
            lambda _: True,
        )
        receipt = registry.invoke("slow", {"value": 1}, context)
        self.assertFalse(receipt.success)
        self.assertEqual(receipt.error.code, ToolFailureCode.TIMEOUT)


if __name__ == "__main__":
    unittest.main()
