"""整图 OCR：校验路径后走独立 OCR 运行时，只返回纯文本。"""

from __future__ import annotations

from max_gui.config import Settings
from max_gui.inference.images import ImagePrepError, prepare_image
from max_gui.inference.ocr import OCR_PROMPT, OcrRuntime
from max_gui.tools.paths import resolve_ocr_path
from max_gui.tools.protocol import Tool, ToolError

OCR_DESCRIPTION = (
    "当看不清截图上的文字或需要精确抄录时，对一张已有图像做整图 OCR。"
    "不要在每次 screenshot 之后无条件调用。点控件请根据最新截图使用视图像素，不要把 OCR 当作点击工具。"
    "path 可以是截图目录或工作区内的图像。"
)


def ocr_tool(settings: Settings, runtime: OcrRuntime | None = None) -> Tool:
    """构造整图 `ocr` 工具。"""
    engine = runtime or OcrRuntime(settings)

    async def recognize(args: dict) -> str:
        """对图像做整图识别。参数：`path`。"""
        path = resolve_ocr_path(
            settings.workspace, settings.screenshots_dir, str(args.get("path") or "")
        )
        if not path.is_file():
            raise ToolError(f"图像不存在：{path}")
        try:
            prepared = prepare_image(
                path, max_edge=settings.max_image_edge, max_bytes=settings.max_image_bytes
            )
        except ImagePrepError as exc:
            raise ToolError(str(exc)) from exc
        return await engine.recognize(path, prepared.part, prompt=OCR_PROMPT)

    return Tool(
        name="ocr",
        description=OCR_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        invoke=recognize,
    )


def ocr_tools(settings: Settings, runtime: OcrRuntime | None = None) -> list[Tool]:
    """注册整图 `ocr`。"""
    return [ocr_tool(settings, runtime)]
