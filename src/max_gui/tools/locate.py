"""界面定位工具 `locate`：OmniParser 出框，画编号并写入命中表。"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from max_gui.config import Settings
from max_gui.inference.omniparser import (
    LOCATE_EMPTY_MESSAGE,
    LOCATE_SKIP_MESSAGE,
    LocateRuntime,
    LocateUnavailable,
)
from max_gui.tools.desktop import active_view_frame, store_locate_hits
from max_gui.tools.overlay import project_and_draw, select_boxes
from max_gui.tools.paths import resolve_ocr_path
from max_gui.tools.protocol import Tool, ToolError, ToolResult

LOCATE_DESCRIPTION = (
    "对当前截图做可点击控件定位：返回最多 40 个编号、标签、视图像素中心，并回注带框图。"
    "点图标或按钮时优先调用，再用 mouse_move 的 target_id。"
    "可省略 path（默认最近一张截图）。需要抄字时用 ocr，不要用本工具。"
)


def locate_tool(settings: Settings, runtime: LocateRuntime | None = None) -> Tool:
    """构造 `locate` 工具。"""
    engine = runtime or LocateRuntime(settings)

    async def locate(args: dict) -> ToolResult | str:
        """检测可点控件并画编号。参数：可选 `path`。"""
        path = _resolve_locate_path(settings, str(args.get("path") or ""))
        if not path.is_file():
            raise ToolError(f"图像不存在：{path}")
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
            return LOCATE_EMPTY_MESSAGE
        items, hits, overlay = project_and_draw(path, chosen, settings=settings)
        store_locate_hits(hits)
        stamp = path.stem
        out = Path(settings.screenshots_dir) / f"{stamp}-boxes.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        overlay.save(out)
        payload = {
            "items": [
                {
                    "id": item.id,
                    "label": item.label,
                    "role": item.role,
                    "view": item.view,
                    "logical": item.logical,
                }
                for item in items
            ],
            "path": str(out),
            "coordinate_space": "view",
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
