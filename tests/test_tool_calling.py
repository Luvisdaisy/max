import unittest
from unittest.mock import Mock

from PIL import Image
from pydantic import BaseModel

from max_agent.orchestration.tool_calling import (
    ReadOnlyToolExplainer,
    ToolSelectionError,
)
from max_agent.tools.base import ToolFailureCode, ToolReceipt
from max_agent.tools.perception.screen import ObserveScreenTool
from max_agent.tools.registry import ToolRegistry


class _RequiredInput(BaseModel):
    """测试工具的必填输入，用于确认校验失败不会到达工具实现。"""

    value: int


class _RequiredTool:
    """只接受整数输入的测试工具。"""

    name = "required_tool"
    input_model = _RequiredInput

    def invoke(self, tool_input: _RequiredInput) -> ToolReceipt:
        raise AssertionError("无效输入不得执行工具")


class _EmptyInput(BaseModel):
    """无需参数的测试工具输入。"""


class _UnavailableTool:
    """返回含敏感底层信息的失败回执，验证业务边界会完成净化。"""

    name = "unavailable_tool"
    input_model = _EmptyInput

    def __init__(self, message: str) -> None:
        self._message = message

    def invoke(self, tool_input: _EmptyInput) -> ToolReceipt:
        return ToolReceipt.failure(
            self.name, ToolFailureCode.UNAVAILABLE, self._message
        )


class ToolCallingTests(unittest.TestCase):
    """验证只读工具循环与 UI 状态边界不会泄漏观察数据。"""

    def test_model_selects_screen_tool_and_receipt_redacts_image(self) -> None:
        registry = ToolRegistry()
        registry.register(
            ObserveScreenTool(
                capture=lambda _: {
                    "image": Image.new("RGB", (1, 1)),
                    "width": 1,
                    "height": 1,
                    "bounds": {},
                    "dpi": None,
                }
            )
        )
        result = ReadOnlyToolExplainer(
            registry,
            select=lambda goal, tools: {"tool_name": "observe_screen"},
            explain=lambda goal, observation: "桌面为空白。",
        ).run("解释当前桌面")

        self.assertEqual(result.text, "桌面为空白。")
        self.assertEqual(result.tool_name, "observe_screen")
        self.assertNotIn("image", result.receipt)

    def test_unknown_tool_becomes_sanitized_observation(self) -> None:
        registry = ToolRegistry()
        observations = []
        explainer = ReadOnlyToolExplainer(
            registry,
            select=lambda goal, tools: {"tool_name": "execute_action"},
            explain=lambda goal, observation: (
                observations.append(observation) or "继续回答"
            ),
        )

        result = explainer.run("解释当前桌面")

        self.assertEqual(result.text, "继续回答")
        self.assertEqual(observations[0]["tool_failure"]["code"], "tool_not_allowed")
        self.assertNotIn("execute_action", repr(observations))

    def test_invalid_selection_continues_without_another_tool_attempt(self) -> None:
        registry = ToolRegistry()
        select = Mock(side_effect=ToolSelectionError("sensitive selection output"))
        observations = []

        result = ReadOnlyToolExplainer(
            registry,
            select=select,
            explain=lambda goal, observation: (
                observations.append(observation) or "已恢复"
            ),
        ).run("你好")

        self.assertEqual(result.text, "已恢复")
        self.assertEqual(select.call_count, 1)
        self.assertEqual(
            observations[0]["tool_failure"]["code"], "invalid_tool_selection"
        )
        self.assertNotIn("sensitive selection output", repr(observations))

    def test_invalid_arguments_are_explained_after_failed_tool_event(self) -> None:
        registry = ToolRegistry()
        registry.register(_RequiredTool())
        secret = "sensitive-model-argument"
        observations = []
        events = []

        result = ReadOnlyToolExplainer(
            registry,
            select=lambda goal, tools: {
                "tool_name": "required_tool",
                "arguments": {"secret": secret},
            },
            explain=lambda goal, observation: (
                observations.append(observation) or "仍然回答用户"
            ),
            on_tool_event=lambda name, state, elapsed: events.append(
                (name, state, elapsed)
            ),
        ).run("你好")

        self.assertEqual(result.text, "仍然回答用户")
        self.assertEqual([event[1] for event in events], ["running", "failed"])
        self.assertEqual(
            observations[0]["tool_failure"],
            {
                "code": "invalid_input",
                "summary": "工具输入不符合调用契约。",
                "tool_name": "required_tool",
            },
        )
        self.assertNotIn(secret, repr(observations))

    def test_raw_tool_failure_is_not_forwarded_to_final_explanation(self) -> None:
        registry = ToolRegistry()
        secret = "C:/private/model/path and raw exception"
        registry.register(_UnavailableTool(secret))
        observations = []

        result = ReadOnlyToolExplainer(
            registry,
            select=lambda goal, tools: {"tool_name": "unavailable_tool"},
            explain=lambda goal, observation: (
                observations.append(observation) or "说明限制后继续回答"
            ),
        ).run("继续处理")

        self.assertEqual(result.text, "说明限制后继续回答")
        self.assertEqual(observations[0]["tool_failure"]["summary"], "工具当前不可用。")
        self.assertNotIn(secret, repr(observations))

    def test_tool_events_only_expose_name_state_and_elapsed_time(self) -> None:
        registry = ToolRegistry()
        secret = "sensitive-pixel-payload"
        registry.register(
            ObserveScreenTool(
                capture=lambda _: {
                    "image": Image.new("RGB", (1, 1)),
                    "width": 1,
                    "height": 1,
                    "bounds": {"secret": secret},
                    "dpi": None,
                }
            )
        )
        events: list[tuple[str, str, float]] = []

        ReadOnlyToolExplainer(
            registry,
            select=lambda goal, tools: {
                "tool_name": "observe_screen",
                "arguments": {"untrusted": secret},
            },
            explain=lambda goal, observation: "完成",
            on_tool_event=lambda name, state, elapsed: events.append(
                (name, state, elapsed)
            ),
        ).run("解释当前桌面")

        self.assertEqual([event[1] for event in events], ["running", "succeeded"])
        self.assertTrue(all(event[0] == "observe_screen" for event in events))
        self.assertTrue(all(event[2] >= 0 for event in events))
        self.assertNotIn(secret, repr(events))
