"""推理客户端与图像预处理。

对外符号：
- `InferenceClient`：调用 OpenAI 兼容流式接口（本机 vLLM 或魔搭 API-Inference）。
- `ChatDelta`：一次流式增量（正文、思考、工具调用、结束原因）。
- `ConnectionFailedError`：服务不可达，提示先 `max-gui serve`。
- `prepare_image` / `PreparedImage` / `ImagePrepError`：缩放编码图像并报告尺寸，或拒绝无效文件。
- `OcrRuntime`：懒启动 OCR vLLM 与 transformers 回退。
- `parse_spotting`：解析 `Spotting:` 输出为文字行框。
"""

from max_gui.inference.client import ChatDelta, ConnectionFailedError, InferenceClient
from max_gui.inference.images import ImagePrepError, PreparedImage, prepare_image
from max_gui.inference.ocr import OcrRuntime, shutdown_owned_ocr
from max_gui.inference.spotting import SpottingParseError, parse_spotting

__all__ = [
    "ChatDelta",
    "ConnectionFailedError",
    "ImagePrepError",
    "InferenceClient",
    "OcrRuntime",
    "PreparedImage",
    "SpottingParseError",
    "parse_spotting",
    "prepare_image",
    "shutdown_owned_ocr",
]
