"""验证感知工具只处理显式输入，并且注册表保持工具契约。"""

import unittest
from pathlib import Path

from PIL import Image, ImageDraw
from pydantic import BaseModel

from max_agent.tools.base import ToolFailureCode, ToolReceipt
from max_agent.tools.perception.ocr import RecognizeTextTool
from max_agent.tools.perception.screen import ObserveScreenTool
from max_agent.tools.perception.som import AnnotateSomTool
from max_agent.tools.perception.uia import ObserveUiElementsTool
from max_agent.tools.perception.vision import MatchTemplateTool, PreprocessImageTool
from max_agent.tools.registry import ToolRegistry, build_default_registry


class _EchoInput(BaseModel):
    value: int


class _EchoTool:
    name = "echo"
    input_model = _EchoInput

    def invoke(self, tool_input: _EchoInput) -> ToolReceipt:
        return ToolReceipt(
            tool_name=self.name, success=True, data={"value": tool_input.value}
        )


class PerceptionToolTests(unittest.TestCase):
    def test_registry_validates_and_contains_default_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(_EchoTool())

        self.assertEqual(registry.invoke("echo", {"value": 3}).data, {"value": 3})
        self.assertEqual(
            registry.invoke("echo", {}).error.code, ToolFailureCode.INVALID_INPUT
        )
        self.assertEqual(
            registry.invoke("missing", {}).error.code, ToolFailureCode.UNKNOWN_TOOL
        )
        self.assertEqual(
            set(build_default_registry().names),
            {
                "observe_screen",
                "recognize_text",
                "observe_ui_elements",
                "preprocess_image",
                "match_template",
                "annotate_som",
            },
        )

    def test_screen_tool_returns_in_memory_image_and_rejects_missing_monitor(
        self,
    ) -> None:
        image = Image.new("RGB", (4, 3), "white")
        tool = ObserveScreenTool(
            lambda index: (
                {
                    "image": image,
                    "width": 4,
                    "height": 3,
                    "bounds": {"left": 0, "top": 0, "width": 4, "height": 3},
                    "dpi": 96,
                }
                if index == 1
                else (_ for _ in ()).throw(IndexError("monitor 0 is unavailable"))
            )
        )

        receipt = tool.invoke(tool.input_model(monitor_index=1))

        self.assertTrue(receipt.success)
        self.assertIs(receipt.data["image"], image)
        self.assertEqual(receipt.data["dpi"], 96)
        self.assertEqual(
            tool.invoke(tool.input_model()).error.code, ToolFailureCode.UNAVAILABLE
        )

    def test_ocr_requires_configured_local_models_and_returns_lines(self) -> None:
        tool = RecognizeTextTool()
        unavailable = tool.invoke(tool.input_model(image=Image.new("RGB", (2, 2))))
        self.assertEqual(unavailable.error.code, ToolFailureCode.UNAVAILABLE)

        class _Page:
            json = {"res": {"rec_texts": ["MAX"]}}

        class _Engine:
            def predict(self, image: Image.Image) -> list[_Page]:
                return [_Page()]

        local_tool = RecognizeTextTool(Path("."), engine_factory=lambda _: _Engine())
        receipt = local_tool.invoke(
            local_tool.input_model(image=Image.new("RGB", (2, 2)))
        )
        self.assertEqual(receipt.data["lines"][0]["text"], "MAX")

    def test_uia_tool_uses_observer_without_window_activation(self) -> None:
        tool = ObserveUiElementsTool(
            lambda process_id, max_elements: [
                {
                    "name": "Save",
                    "role": "Button",
                    "bounds": {"left": 1, "top": 2, "width": 3, "height": 4},
                    "enabled": True,
                }
            ]
        )

        receipt = tool.invoke(tool.input_model(process_id=42))

        self.assertTrue(receipt.success)
        self.assertEqual(receipt.data["elements"][0]["name"], "Save")
        failing = ObserveUiElementsTool(
            lambda process_id, max_elements: (_ for _ in ()).throw(
                RuntimeError("denied")
            )
        ).invoke(tool.input_model(process_id=42))
        self.assertEqual(failing.error.code, ToolFailureCode.UNAVAILABLE)

    def test_vision_and_som_tools_process_only_supplied_images(self) -> None:
        image = Image.new("RGB", (20, 20), "white")
        ImageDraw.Draw(image).rectangle((5, 6, 9, 10), fill="black")
        template = image.crop((5, 6, 10, 11))

        preprocessed = PreprocessImageTool().invoke(
            PreprocessImageTool.input_model(image=image, threshold=128)
        )
        matched = MatchTemplateTool().invoke(
            MatchTemplateTool.input_model(
                image=image, template=template, minimum_score=0.9
            )
        )
        annotated = AnnotateSomTool().invoke(
            AnnotateSomTool.input_model(
                image=image,
                marks=[{"label": "1", "left": 5, "top": 6, "width": 5, "height": 5}],
            )
        )

        self.assertTrue(preprocessed.success)
        self.assertTrue(matched.success)
        self.assertTrue(matched.data["matches"])
        self.assertEqual(annotated.data["annotations"][0]["label"], "1")


if __name__ == "__main__":
    unittest.main()
