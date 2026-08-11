"""本地 OCR 工具：解析任务内图像引用并返回坐标化文字。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, model_validator

from max_agent.orchestration.resources import ResourceError, ResourceRef
from max_agent.tools.base import (
    ToolContext,
    ToolFailureCode,
    ToolPermission,
    ToolPhase,
    ToolReceipt,
)


class RecognizeTextInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image_ref: ResourceRef | None = None
    image: Image.Image | None = None
    region: dict[str, int] | None = None

    @model_validator(mode="after")
    def require_source(self) -> "RecognizeTextInput":
        if (self.image_ref is None) == (self.image is None):
            raise ValueError("provide exactly one image_ref or image")
        return self


class RecognizeTextTool:
    name = "recognize_text"
    description = "Recognize text in a task image and return confidence and bounds."
    permission = ToolPermission.OBSERVE
    allowed_phases = frozenset({ToolPhase.TOOL, ToolPhase.OBSERVE_AFTER_ACTION})
    timeout_seconds = 30.0
    recoverable = True
    model_visible = True
    side_effect = False
    read_only = True
    input_model = RecognizeTextInput

    def __init__(
        self,
        model_dir: Path | object | None = None,
        engine_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self._model_dir = (
            Path(model_dir) if isinstance(model_dir, (str, Path)) else None
        )
        self._engine_factory = engine_factory or _create_local_engine
        self._engine: Any | None = None

    def invoke(
        self, tool_input: RecognizeTextInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        try:
            image = tool_input.image or (
                context.resources.get(tool_input.image_ref, context.task_id, "image")
                if context is not None and tool_input.image_ref is not None
                else None
            )
        except ResourceError as error:
            return ToolReceipt.failure(
                self.name, ToolFailureCode.INVALID_INPUT, str(error)
            )
        if image is None:
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.INVALID_INPUT,
                "image_ref requires task context",
            )
        if self._model_dir is None or not self._model_dir.is_dir():
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.UNAVAILABLE,
                "local PaddleOCR model directory is not configured",
            )
        offset_x = offset_y = 0
        if tool_input.region is not None:
            try:
                offset_x = int(tool_input.region["left"])
                offset_y = int(tool_input.region["top"])
                width = int(tool_input.region["width"])
                height = int(tool_input.region["height"])
                image = image.crop(
                    (offset_x, offset_y, offset_x + width, offset_y + height)
                )
            except (KeyError, TypeError, ValueError):
                return ToolReceipt.failure(
                    self.name, ToolFailureCode.INVALID_INPUT, "invalid OCR region"
                )
        try:
            self._engine = self._engine or self._engine_factory(self._model_dir)
            # PaddleOCR 3.7 不接受 PIL.Image；在内存中转换即可保持截图不落盘。
            result = self._engine.predict(np.asarray(image.convert("RGB")))
            return ToolReceipt(
                tool_name=self.name,
                success=True,
                data={"lines": _lines(result, offset_x, offset_y)},
            )
        except Exception as error:
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.UNAVAILABLE,
                f"local OCR failed: {type(error).__name__}",
            )


def _create_local_engine(model_dir: Path) -> Any:
    from paddleocr import PaddleOCR

    det_dir = model_dir / "det"
    rec_dir = model_dir / "rec"
    if not det_dir.is_dir() or not rec_dir.is_dir():
        raise FileNotFoundError(
            "local PaddleOCR det/ and rec/ model directories are required"
        )
    return PaddleOCR(
        # PaddleOCR 3.7 的默认模型可能随版本升级；名称必须与随仓库准备的
        # PP-OCRv5 mobile 推理目录一致，否则框架会把本地目录判为不匹配。
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_detection_model_dir=str(det_dir),
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        text_recognition_model_dir=str(rec_dir),
        # 桌面文字主路径只需要检测与识别。显式关闭可选文档处理模块，
        # 防止 PaddleOCR 在离线运行时为默认流水线查找或下载额外模型。
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        # Paddle 3.2 的 Windows CPU oneDNN 执行器无法运行该 v5 图中的
        # ArrayAttribute<Double>；关闭 oneDNN 后仍是完全本地的 CPU 推理。
        enable_mkldnn=False,
    )


def _lines(
    result: Any, offset_x: int = 0, offset_y: int = 0
) -> list[dict[str, object]]:
    lines: list[dict[str, object]] = []
    for page in result:
        payload = page.json if hasattr(page, "json") else page
        recognized = payload.get("res", payload)
        texts = recognized.get("rec_texts", [])
        scores = recognized.get("rec_scores", [])
        boxes = recognized.get("rec_boxes", recognized.get("rec_polys", []))
        for index, text in enumerate(texts):
            bounds = boxes[index] if index < len(boxes) else None
            if bounds is not None:
                bounds = _offset_bounds(bounds, offset_x, offset_y)
            lines.append(
                {
                    "text": str(text),
                    "confidence": float(scores[index]) if index < len(scores) else None,
                    "bounds": bounds,
                }
            )
    return lines


def _offset_bounds(bounds: Any, x: int, y: int) -> Any:
    if isinstance(bounds, dict):
        return {
            **bounds,
            "left": int(bounds.get("left", 0)) + x,
            "top": int(bounds.get("top", 0)) + y,
        }
    if isinstance(bounds, (list, tuple)):
        if len(bounds) == 4 and all(
            isinstance(value, (int, float)) for value in bounds
        ):
            return [bounds[0] + x, bounds[1] + y, bounds[2] + x, bounds[3] + y]
        return [[point[0] + x, point[1] + y] for point in bounds]
    return bounds
