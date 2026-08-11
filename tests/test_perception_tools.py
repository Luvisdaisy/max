"""验证感知工具只处理显式输入，并且注册表保持工具契约。"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel

from max_agent.orchestration.models import CancellationToken
from max_agent.orchestration.observation import ObservationService
from max_agent.orchestration.resources import InMemoryResourceStore, ResourceRef
from max_agent.tools.base import ToolContext, ToolFailureCode, ToolPhase, ToolReceipt
from max_agent.tools.perception.ocr import RecognizeTextTool, _create_local_engine
from max_agent.tools.perception.screen import ObserveScreenTool
from max_agent.tools.perception.som import AnnotateSomTool
from max_agent.tools.perception.uia import ObserveUiElementsTool, ObserveWindowsTool
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
                "observe_windows",
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
            def predict(self, image: np.ndarray) -> list[_Page]:
                self.received_array = isinstance(image, np.ndarray)
                return [_Page()]

        engine = _Engine()
        local_tool = RecognizeTextTool(Path("."), engine_factory=lambda _: engine)
        receipt = local_tool.invoke(
            local_tool.input_model(image=Image.new("RGB", (2, 2)))
        )
        self.assertEqual(receipt.data["lines"][0]["text"], "MAX")
        self.assertTrue(engine.received_array)

    def test_local_ocr_engine_disables_optional_model_pipelines(self) -> None:
        """离线桌面 OCR 不得因 PaddleOCR 默认值再请求额外模型。"""
        with TemporaryDirectory() as temporary:
            model_dir = Path(temporary)
            (model_dir / "det").mkdir()
            (model_dir / "rec").mkdir()
            with patch("paddleocr.PaddleOCR", return_value=object()) as constructor:
                _create_local_engine(model_dir)

        constructor.assert_called_once_with(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_detection_model_dir=str(model_dir / "det"),
            text_recognition_model_name="PP-OCRv5_mobile_rec",
            text_recognition_model_dir=str(model_dir / "rec"),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
        )

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

    def test_task_context_returns_image_ref_and_rejects_cross_task_use(self) -> None:
        store = InMemoryResourceStore()
        context = ToolContext(
            "task-a",
            ToolPhase.TOOL,
            store,
            CancellationToken(),
            lambda _: True,
        )
        screen = ObserveScreenTool(
            lambda _: {
                "image": Image.new("RGB", (8, 6), "white"),
                "width": 8,
                "height": 6,
                "bounds": {"left": 10, "top": 20, "width": 8, "height": 6},
                "dpi": 120,
            },
            foreground=lambda: None,
        ).invoke(ObserveScreenTool.input_model(), context)
        ref = ResourceRef.model_validate(screen.data["image_ref"])
        self.assertEqual(store.count("task-a"), 1)
        self.assertNotIn("image", screen.data)

        class _Engine:
            def predict(self, image: Image.Image) -> list[dict[str, object]]:
                return [
                    {
                        "res": {
                            "rec_texts": ["MAX"],
                            "rec_scores": [0.9],
                            "rec_boxes": [[1, 2, 4, 5]],
                        }
                    }
                ]

        ocr = RecognizeTextTool(Path("."), engine_factory=lambda _: _Engine())
        receipt = ocr.invoke(ocr.input_model(image_ref=ref), context)
        self.assertEqual(receipt.data["lines"][0]["bounds"], [1, 2, 4, 5])
        other = ToolContext(
            "task-b", ToolPhase.TOOL, store, CancellationToken(), lambda _: True
        )
        self.assertEqual(
            ocr.invoke(ocr.input_model(image_ref=ref), other).error.code,
            ToolFailureCode.INVALID_INPUT,
        )

    def test_window_discovery_returns_stable_identity_without_activation(self) -> None:
        tool = ObserveWindowsTool(
            lambda _: [
                {
                    "hwnd": 7,
                    "process_id": 42,
                    "executable_path": "C:/Windows/notepad.exe",
                    "title": "Notes",
                    "bounds": {"left": 0, "top": 0, "width": 100, "height": 80},
                    "foreground": False,
                    "taskbar_visible": True,
                }
            ]
        )
        receipt = tool.invoke(tool.input_model())
        self.assertEqual(receipt.data["windows"][0]["hwnd"], 7)
        self.assertTrue(receipt.data["windows"][0]["taskbar_visible"])

    def test_observation_service_runs_screen_windows_and_ocr_then_reuses_unchanged_frame(
        self,
    ) -> None:
        registry = ToolRegistry()
        image = Image.new("RGB", (8, 6), "white")
        registry.register(
            ObserveScreenTool(
                lambda _: {
                    "image": image.copy(),
                    "width": 8,
                    "height": 6,
                    "bounds": {"left": 0, "top": 0, "width": 8, "height": 6},
                    "dpi": 96,
                },
                foreground=lambda: None,
            )
        )
        registry.register(ObserveWindowsTool(lambda _: []))

        class _Engine:
            calls = 0

            def predict(self, source: Image.Image) -> list[dict[str, object]]:
                self.calls += 1
                return [{"res": {"rec_texts": ["MAX"], "rec_boxes": [[0, 0, 3, 2]]}}]

        engine = _Engine()
        registry.register(RecognizeTextTool(Path("."), engine_factory=lambda _: engine))
        store = InMemoryResourceStore()
        context = ToolContext(
            "task", ToolPhase.TOOL, store, CancellationToken(), lambda _: True
        )
        service = ObservationService(registry)

        first, first_receipts = service.observe(context)
        second, second_receipts = service.observe(context, first)

        self.assertEqual(
            [item.tool_name for item in first_receipts],
            ["observe_windows", "observe_screen", "recognize_text"],
        )
        self.assertEqual(first.ocr_lines[0]["text"], "MAX")
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertTrue(second_receipts[-1].data["reused"])
        self.assertEqual(engine.calls, 1)

    def test_changed_region_ocr_keeps_bounded_visual_context(self) -> None:
        """新增字形的局部 OCR 框应保留背景，且不得越过截图边界。"""
        registry = ToolRegistry()
        images = [Image.new("RGB", (100, 80), "white") for _ in range(2)]
        ImageDraw.Draw(images[1]).rectangle((45, 35, 50, 40), fill="black")
        registry.register(
            ObserveScreenTool(
                lambda _: {
                    "image": images.pop(0),
                    "width": 100,
                    "height": 80,
                    "bounds": {"left": 0, "top": 0, "width": 100, "height": 80},
                    "dpi": 96,
                },
                foreground=lambda: None,
            )
        )
        registry.register(ObserveWindowsTool(lambda _: []))

        class _OcrTool:
            name = "recognize_text"
            input_model = RecognizeTextTool.input_model
            allowed_phases = frozenset({ToolPhase.TOOL, ToolPhase.OBSERVE_AFTER_ACTION})

            def __init__(self) -> None:
                self.regions: list[dict[str, int] | None] = []

            def invoke(self, tool_input, context=None) -> ToolReceipt:
                self.regions.append(tool_input.region)
                return ToolReceipt(
                    tool_name=self.name, success=True, data={"lines": []}
                )

        ocr = _OcrTool()
        registry.register(ocr)
        context = ToolContext(
            "task",
            ToolPhase.TOOL,
            InMemoryResourceStore(),
            CancellationToken(),
            lambda _: True,
        )
        service = ObservationService(registry)

        first, _ = service.observe(context)
        service.observe(context, first)

        self.assertEqual(
            ocr.regions,
            [None, {"left": 21, "top": 11, "width": 54, "height": 54}],
        )


if __name__ == "__main__":
    unittest.main()
