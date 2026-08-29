"""推理客户端、上下文预算与图像预处理。

对外符号：
- `InferenceClient`：调用 OpenAI 兼容流式接口（本机 vLLM 或魔搭 API-Inference）。
- `ChatDelta`：一次流式增量（正文、思考、工具调用、结束原因、可选用量）。
- `TokenUsage`：接口回传的输入/输出/合计 token。
- `ConnectionFailedError` / `InferenceRequestError`：最终网络或 HTTP 推理错误。
- `RetryNotice` / `RetryMetadata`：不含请求载荷的重试进度与尝试统计。
- `ContextSelection`：按预算选择后的完整工具链与脱敏计数。
- `ContextBudgetExceededError`：基础请求已超过可用上下文预算。
- `prepare_image` / `PreparedImage` / `ImagePrepError`：缩放编码图像并报告尺寸，或拒绝无效文件。
- `OcrRuntime`：懒启动 OCR vLLM 与 transformers 回退。
- `LocateRuntime`：懒启动 OmniParser 检测进程。
- `parse_spotting`：解析 `Spotting:` 输出为文字行框。
"""

from max_gui.inference.budget import ContextBudgetExceededError, ContextSelection
from max_gui.inference.client import (
    ChatDelta,
    ConnectionFailedError,
    InferenceClient,
    InferenceRequestError,
    TokenUsage,
)
from max_gui.inference.images import ImagePrepError, PreparedImage, prepare_image
from max_gui.inference.ocr import OcrRuntime, shutdown_owned_ocr
from max_gui.inference.omniparser import LocateRuntime, shutdown_owned_locate
from max_gui.inference.retry import RetryMetadata, RetryNotice
from max_gui.inference.spotting import SpottingParseError, parse_spotting

__all__ = [
    "ChatDelta",
    "ConnectionFailedError",
    "ContextBudgetExceededError",
    "ContextSelection",
    "ImagePrepError",
    "InferenceClient",
    "InferenceRequestError",
    "LocateRuntime",
    "OcrRuntime",
    "PreparedImage",
    "RetryMetadata",
    "RetryNotice",
    "SpottingParseError",
    "TokenUsage",
    "parse_spotting",
    "prepare_image",
    "shutdown_owned_locate",
    "shutdown_owned_ocr",
]
