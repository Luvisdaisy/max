"""本地 OCR 工具：仅识别调用方提供的图像，不触发屏幕控制。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel, ConfigDict

from max_agent.tools.base import ToolFailureCode, ToolReceipt


class RecognizeTextInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image: Image.Image


class RecognizeTextTool:
    """将本地 OCR 引擎结果归一化为可审计的文本行回执。"""

    name = "recognize_text"
    input_model = RecognizeTextInput

    def __init__(
        self,
        model_dir: Path | None = None,
        engine_factory: Callable[[Path], Any] | None = None,
    ) -> None:
        self._model_dir = model_dir
        self._engine_factory = engine_factory or _create_local_engine
        self._engine: Any | None = None

    def invoke(self, tool_input: RecognizeTextInput) -> ToolReceipt:
        if self._model_dir is None or not self._model_dir.is_dir():
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.UNAVAILABLE,
                "local PaddleOCR model directory is not configured",
            )
        try:
            self._engine = self._engine or self._engine_factory(self._model_dir)
            result = self._engine.predict(tool_input.image)
            return ToolReceipt(
                tool_name=self.name, success=True, data={"lines": _lines(result)}
            )
        except (
            Exception
        ) as error:  # local OCR failures must not escape or trigger fallback downloads
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.UNAVAILABLE,
                f"{type(error).__name__}: {error}",
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
        text_detection_model_dir=str(det_dir),
        text_recognition_model_dir=str(rec_dir),
    )


def _lines(result: Any) -> list[dict[str, object]]:
    lines: list[dict[str, object]] = []
    for page in result:
        payload = page.json if hasattr(page, "json") else page
        recognized = payload.get("res", payload)
        texts = recognized.get("rec_texts", [])
        scores = recognized.get("rec_scores", [])
        boxes = recognized.get("rec_boxes", recognized.get("rec_polys", []))
        for index, text in enumerate(texts):
            lines.append(
                {
                    "text": str(text),
                    "confidence": float(scores[index]) if index < len(scores) else None,
                    "bounds": boxes[index] if index < len(boxes) else None,
                }
            )
    return lines
