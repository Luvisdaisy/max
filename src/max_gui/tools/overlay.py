"""把检测框投影到视图/逻辑坐标，做 NMS 截断并画编号叠加图。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from max_gui.config import Settings
from max_gui.inference.images import prepare_image
from max_gui.inference.omniparser import DetectedBox
from max_gui.tools.desktop import ViewFrame, active_view_frame

LOCATE_MAX_BOXES = 40
LOCATE_NMS_IOU = 0.5
LOCATE_MIN_SIDE = 4


@dataclass(frozen=True, slots=True)
class ProjectedItem:
    """编号后的一项，含视图/逻辑框，供 JSON 与命中表使用。"""

    id: int
    label: str
    role: str
    view: dict[str, int]
    logical: dict[str, int]
    logical_center: tuple[int, int]


def select_boxes(boxes: list[DetectedBox], *, width: int, height: int) -> list[DetectedBox]:
    """过滤过小框、NMS，再按分数保留最多 40 个。

    参数：
        boxes: 检测器原始框。
        width / height: 原图像素宽高，用于把归一化坐标换成像素再算面积。

    返回：
        截断后、尚未按空间排序的框（仍带原坐标系）。
    """
    scored: list[tuple[float, DetectedBox, tuple[float, float, float, float]]] = []
    for box in boxes:
        px = _pixel_rect(box, width, height)
        if px is None:
            continue
        x1, y1, x2, y2 = px
        if (x2 - x1) < LOCATE_MIN_SIDE or (y2 - y1) < LOCATE_MIN_SIDE:
            continue
        area = (x2 - x1) * (y2 - y1)
        score = box.score if box.score else area
        scored.append((score, box, px))
    scored.sort(key=lambda item: item[0], reverse=True)
    kept: list[tuple[float, DetectedBox, tuple[float, float, float, float]]] = []
    for item in scored:
        if any(_iou(item[2], other[2]) >= LOCATE_NMS_IOU for other in kept):
            continue
        kept.append(item)
        if len(kept) >= LOCATE_MAX_BOXES:
            break
    kept.sort(key=lambda item: (item[2][1], item[2][0]))
    return [item[1] for item in kept]


def project_and_draw(
    source_path: Path,
    boxes: list[DetectedBox],
    *,
    settings: Settings,
) -> tuple[list[ProjectedItem], dict[int, tuple[int, int]], Image.Image]:
    """把框映到当前视图，画编号，并给出逻辑中心表。

    参数：
        source_path: 原截图。
        boxes: 已截断的检测框。
        settings: 图像预处理上限，无视图帧时用来估视图尺寸。

    返回：
        `(JSON 项, id→逻辑中心, 叠加图)`。
    """
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
    items: list[ProjectedItem] = []
    hits: dict[int, tuple[int, int]] = {}
    for index, box in enumerate(boxes, start=1):
        sx1, sy1, sx2, sy2 = _source_rect(box, src_w, src_h)
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
        item = ProjectedItem(
            id=index,
            label=box.label,
            role=box.role,
            view=_rect(vx1, vy1, vx2, vy2, vcx, vcy),
            logical=_rect(lx1, ly1, lx2, ly2, lcx, lcy),
            logical_center=(round(lcx), round(lcy)),
        )
        items.append(item)
        hits[index] = item.logical_center
        draw.rectangle((vx1, vy1, vx2, vy2), outline=(255, 220, 40), width=2)
        label = str(index)
        tx, ty = int(vx1) + 2, max(0, int(vy1) - 12)
        draw.rectangle((tx, ty, tx + 8 * len(label) + 4, ty + 12), fill=(255, 220, 40))
        draw.text((tx + 2, ty), label, fill=(0, 0, 0), font=font)
    return items, hits, overlay


def _source_rect(box: DetectedBox, src_w: int, src_h: int) -> tuple[float, float, float, float]:
    """把检测框换到原图像素。"""
    if box.normalized:
        return box.x1 * src_w, box.y1 * src_h, box.x2 * src_w, box.y2 * src_h
    return box.x1, box.y1, box.x2, box.y2


def _pixel_rect(
    box: DetectedBox, width: int, height: int
) -> tuple[float, float, float, float] | None:
    """原图像素矩形；退化框返回 `None`。"""
    x1, y1, x2, y2 = _source_rect(box, width, height)
    left, right = min(x1, x2), max(x1, x2)
    top, bottom = min(y1, y2), max(y1, y2)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """两个像素框的交并比。"""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


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
