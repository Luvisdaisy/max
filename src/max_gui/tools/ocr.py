"""整图 OCR 与文字定位：校验路径后走独立 OCR 运行时。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from max_gui.config import Settings
from max_gui.inference.images import ImagePrepError, prepare_image
from max_gui.inference.ocr import (
    OCR_LOCATE_PARSE_MESSAGE,
    OCR_LOCATE_SKIP_MESSAGE,
    OCR_PROMPT,
    SPOTTING_MAX_NEW_TOKENS,
    SPOTTING_PROMPT,
    OcrRuntime,
)
from max_gui.inference.spotting import SpotBox, SpottingParseError, parse_spotting
from max_gui.tools.desktop import ViewFrame, active_view_frame, store_locate_hits
from max_gui.tools.paths import resolve_ocr_path
from max_gui.tools.protocol import Tool, ToolError, ToolResult

OCR_DESCRIPTION = (
    "当看不清截图上的文字或需要精确抄录时，对一张已有图像做整图 OCR。"
    "不要在每次 screenshot 之后无条件调用。path 可以是截图目录或工作区内的图像。"
)
LOCATE_DESCRIPTION = (
    "对已有截图做文字行定位：返回编号、文本、视图像素中心，并回注带框图。"
    "只框有字的行，不识别无文字图标。密界面请先对区域截图再调用。"
)
SPOTTING_UPSCALE = 1500


def ocr_tool(settings: Settings, runtime: OcrRuntime | None = None) -> Tool:
    """构造整图 `ocr` 工具。"""
    engine = runtime or OcrRuntime(settings)

    async def recognize(args: dict) -> str:
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


def ocr_locate_tool(settings: Settings, runtime: OcrRuntime | None = None) -> Tool:
    """构造 `ocr_locate`：spotting、画框、记录可点中心。"""
    engine = runtime or OcrRuntime(settings)

    async def locate(args: dict) -> ToolResult | str:
        """对图像做 spotting，画编号框并记下逻辑中心。参数：`path`。"""
        path = resolve_ocr_path(
            settings.workspace, settings.screenshots_dir, str(args.get("path") or "")
        )
        if not path.is_file():
            raise ToolError(f"图像不存在：{path}")
        send_path, cleanup = _spotting_source(path)
        try:
            try:
                prepared = prepare_image(
                    send_path,
                    max_edge=settings.max_image_edge,
                    max_bytes=settings.max_image_bytes,
                )
            except ImagePrepError as exc:
                raise ToolError(str(exc)) from exc
            raw = await engine.recognize(
                send_path,
                prepared.part,
                prompt=SPOTTING_PROMPT,
                max_new_tokens=SPOTTING_MAX_NEW_TOKENS,
                skip_message=OCR_LOCATE_SKIP_MESSAGE,
            )
        finally:
            if cleanup is not None:
                cleanup.unlink(missing_ok=True)
        if raw == OCR_LOCATE_SKIP_MESSAGE:
            return raw
        try:
            boxes = parse_spotting(_strip_fallback_note(raw))
        except SpottingParseError:
            return OCR_LOCATE_PARSE_MESSAGE
        items, hits, overlay = _project_and_draw(
            path,
            boxes,
            ocr_width=prepared.width,
            ocr_height=prepared.height,
            settings=settings,
        )
        if not items:
            return OCR_LOCATE_PARSE_MESSAGE
        store_locate_hits(hits)
        stamp = path.stem
        out = Path(settings.screenshots_dir) / f"{stamp}-boxes.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(out)
        payload = {
            "items": items,
            "path": str(out),
            "coordinate_space": "view",
        }
        return ToolResult(text=json.dumps(payload, ensure_ascii=False), images=[out])

    return Tool(
        name="ocr_locate",
        description=LOCATE_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        invoke=locate,
    )


def ocr_tools(settings: Settings, runtime: OcrRuntime | None = None) -> list[Tool]:
    """共用一个 OCR 运行时注册 `ocr` 与 `ocr_locate`。"""
    engine = runtime or OcrRuntime(settings)
    return [ocr_tool(settings, engine), ocr_locate_tool(settings, engine)]


def _strip_fallback_note(text: str) -> str:
    """去掉回退标注，避免干扰解析。"""
    marker = "（已回退 transformers）"
    return text.replace(marker, "").strip()


def _spotting_source(path: Path) -> tuple[Path, Path | None]:
    """小图按官方约定放大一倍，返回 `(送去推理的路径, 需要删除的临时文件)`。"""
    with Image.open(path) as image:
        image.load()
        width, height = image.size
        if width >= SPOTTING_UPSCALE or height >= SPOTTING_UPSCALE:
            return path, None
        scaled = image.convert("RGB").resize((width * 2, height * 2), Image.Resampling.LANCZOS)
    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    temp = Path(handle.name)
    handle.close()
    scaled.save(temp)
    return temp, temp


def _project_and_draw(
    source_path: Path,
    boxes: list[SpotBox],
    *,
    ocr_width: int,
    ocr_height: int,
    settings: Settings,
) -> tuple[list[dict], dict[int, tuple[int, int]], Image.Image]:
    """把 spotting 框映到视图/逻辑坐标，并在视图尺寸图上画编号。"""
    with Image.open(source_path) as image:
        source = image.convert("RGB")
    src_w, src_h = source.size
    frame = active_view_frame()
    view_w, view_h, origin_x, origin_y, logical_w, logical_h = _frame_or_source(
        source_path, source.size, frame, settings
    )
    overlay = source.resize((max(1, view_w), max(1, view_h)), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()
    items: list[dict] = []
    hits: dict[int, tuple[int, int]] = {}
    for index, box in enumerate(boxes, start=1):
        sx1 = box.x1 / ocr_width * src_w if ocr_width else box.x1
        sy1 = box.y1 / ocr_height * src_h if ocr_height else box.y1
        sx2 = box.x2 / ocr_width * src_w if ocr_width else box.x2
        sy2 = box.y2 / ocr_height * src_h if ocr_height else box.y2
        vx1 = sx1 / src_w * view_w if src_w else sx1
        vy1 = sy1 / src_h * view_h if src_h else sy1
        vx2 = sx2 / src_w * view_w if src_w else sx2
        vy2 = sy2 / src_h * view_h if src_h else sy2
        lx1 = origin_x + sx1 / src_w * logical_w if src_w else sx1
        ly1 = origin_y + sy1 / src_h * logical_h if src_h else sy1
        lx2 = origin_x + sx2 / src_w * logical_w if src_w else sx2
        ly2 = origin_y + sy2 / src_h * logical_h if src_h else sy2
        vcx, vcy = (vx1 + vx2) / 2, (vy1 + vy2) / 2
        lcx, lcy = (lx1 + lx2) / 2, (ly1 + ly2) / 2
        item = {
            "id": index,
            "text": box.text,
            "view": _rect(vx1, vy1, vx2, vy2, vcx, vcy),
            "logical": _rect(lx1, ly1, lx2, ly2, lcx, lcy),
        }
        items.append(item)
        hits[index] = (round(lcx), round(lcy))
        draw.rectangle((vx1, vy1, vx2, vy2), outline=(255, 220, 40), width=2)
        label = str(index)
        tx, ty = int(vx1) + 2, max(0, int(vy1) - 12)
        draw.rectangle((tx, ty, tx + 8 * len(label) + 4, ty + 12), fill=(255, 220, 40))
        draw.text((tx + 2, ty), label, fill=(0, 0, 0), font=font)
    return items, hits, overlay


def _frame_or_source(
    source_path: Path,
    source_size: tuple[int, int],
    frame: ViewFrame | None,
    settings: Settings,
) -> tuple[int, int, int, int, int, int]:
    """优先用最近一次截图帧；否则用该图自己的预处理尺寸当视图。"""
    if frame is not None and frame.image_path.resolve() == source_path.resolve():
        return (
            frame.view_width,
            frame.view_height,
            frame.origin_x,
            frame.origin_y,
            frame.logical_width,
            frame.logical_height,
        )
    prepared = prepare_image(
        source_path, max_edge=settings.max_image_edge, max_bytes=settings.max_image_bytes
    )
    return prepared.width, prepared.height, 0, 0, source_size[0], source_size[1]


def _rect(x1: float, y1: float, x2: float, y2: float, cx: float, cy: float) -> dict[str, int]:
    """把浮点框收成整数摘要。"""
    left, top = round(min(x1, x2)), round(min(y1, y2))
    right, bottom = round(max(x1, x2)), round(max(y1, y2))
    return {
        "x": left,
        "y": top,
        "w": max(0, right - left),
        "h": max(0, bottom - top),
        "cx": round(cx),
        "cy": round(cy),
    }
