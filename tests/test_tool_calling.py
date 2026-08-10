import unittest

from PIL import Image

from max_agent.orchestration.tool_calling import ReadOnlyToolExplainer
from max_agent.tools.perception.screen import ObserveScreenTool
from max_agent.tools.registry import ToolRegistry


class ToolCallingTests(unittest.TestCase):
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

    def test_unknown_tool_is_not_executed(self) -> None:
        registry = ToolRegistry()
        explainer = ReadOnlyToolExplainer(
            registry,
            select=lambda goal, tools: {"tool_name": "execute_action"},
            explain=lambda goal, observation: "unreachable",
        )

        with self.assertRaisesRegex(RuntimeError, "tool_not_allowed"):
            explainer.run("解释当前桌面")
