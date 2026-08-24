"""界面定位工具 `locate`：OmniParser 出框，画编号并写入命中表。"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from max_gui.config import Settings
from max_gui.inference.images import ImagePrepError, prepare_image
from max_gui.inference.omniparser import (
    LOCATE_EMPTY_MESSAGE,
    LOCATE_SKIP_MESSAGE,
    DetectedBox,
    LocateRuntime,
    LocateUnavailable,
)
from max_gui.tools.desktop import ViewFrame, active_view_frame, store_locate_hits
from max_gui.tools.overlay import ProjectedItem, project_and_draw, select_boxes
from max_gui.tools.paths import resolve_ocr_path
from max_gui.tools.protocol import Tool, ToolError, ToolResult

LOCATE_DESCRIPTION = (
    "对当前截图做可点击控件定位：返回最多 40 个编号、标签、视图像素中心，并回注带框图。"
    "点图标或按钮时优先调用，再用 mouse_move 的 target_id。"
    "可省略 path（默认最近一张截图）。仅当前截图的编号可用于 mouse_move；其他图仅供观察。"
    "需要抄字时用 ocr，不要用本工具。"
)


def locate_tool(settings: Settings, runtime: LocateRuntime | None = None) -> Tool:
    """构造 `locate` 工具。"""
    engine = runtime or LocateRuntime(settings)

    async def locate(args: dict) -> ToolResult | str:
        """检测可点控件并画编号。参数：可选 `path`。"""
        path = _resolve_locate_path(settings, str(args.get("path") or ""))
        if not path.is_file():
            raise ToolError(f"图像不存在：{path}")
        frame = active_view_frame()
        executable = frame is not None and frame.image_path.resolve() == path.resolve()
        if not executable:
            store_locate_hits({})
        try:
            boxes = await engine.parse(path)
        except LocateUnavailable as exc:
            detail = str(exc).strip()
            if detail:
                return f"{LOCATE_SKIP_MESSAGE} {detail}"
            return LOCATE_SKIP_MESSAGE
        with Image.open(path) as image:
            width, height = image.size
        chosen = select_boxes(boxes, width=width, height=height)
        if not chosen:
            # 空结果不能继续复用上一轮的编号，避免模型把旧框误当作当前观察。
            store_locate_hits({})
            return LOCATE_EMPTY_MESSAGE
        stamp = path.stem
        out = Path(settings.screenshots_dir) / f"{stamp}-boxes.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        items, hits, _ = _draw_stable_overlay(
            path,
            chosen,
            settings=settings,
            frame=frame if executable else None,
            executable=executable,
            output=out,
        )
        if executable:
            store_locate_hits(hits)
        payload = {
            "items": [_item_payload(item) for item in items],
            "path": str(out),
            "coordinate_space": "view" if executable else "image",
            "observation_only": not executable,
        }
        return ToolResult(text=json.dumps(payload, ensure_ascii=False), images=[out])

    return Tool(
        name="locate",
        description=LOCATE_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "截图路径；省略则使用最近一次截图",
                }
            },
        },
        invoke=locate,
    )


def _resolve_locate_path(settings: Settings, raw: str) -> Path:
    """省略路径时用当前视图帧；否则限制在截图目录或工作区。"""
    text = raw.strip()
    if not text:
        frame = active_view_frame()
        if frame is None or not Path(frame.image_path).is_file():
            raise ToolError("请先调用 screenshot，或提供 path")
        return Path(frame.image_path)
    return resolve_ocr_path(settings.workspace, settings.screenshots_dir, text)


def _draw_stable_overlay(
    path: Path,
    boxes: list[DetectedBox],
    *,
    settings: Settings,
    frame: ViewFrame | None,
    executable: bool,
    output: Path,
) -> tuple[list[ProjectedItem], dict[int, tuple[int, int]], Path]:
    """按最终会被推理层发送的尺寸画带框图。

    PNG 在推理层会再次压成 JPEG。若字节上限导致尺寸缩小，本函数会按缩小后的
    尺寸重投影，直到再次预处理不再改变边长，避免 JSON 坐标与模型所见图不一致。
    """
    view_size: tuple[int, int] | None = None
    for _ in range(4):
        items, hits, overlay = project_and_draw(
            path,
            boxes,
            settings=settings,
            frame=frame,
            include_logical=executable,
            view_size=view_size,
        )
        overlay.save(output)
        try:
            prepared = prepare_image(
                output,
                max_edge=settings.max_image_edge,
                max_bytes=settings.max_image_bytes,
            )
        except ImagePrepError as exc:
            raise ToolError(str(exc)) from exc
        if overlay.size == (prepared.width, prepared.height):
            return items, hits, output
        view_size = (prepared.width, prepared.height)
    raise ToolError("定位框图无法在图像上限内稳定生成，请缩小截图区域后重试")


def _item_payload(item: ProjectedItem) -> dict[str, object]:
    """把定位项收成模型可见 JSON；观察图不伪造逻辑桌面坐标。"""
    payload = {
        "id": item.id,
        "label": item.label,
        "role": item.role,
        "view": item.view,
    }
    if item.logical is not None:
        payload["logical"] = item.logical
    return payload
