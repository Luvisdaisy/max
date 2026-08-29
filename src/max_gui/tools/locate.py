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
from max_gui.tools.dock import DockCandidate, find_dock_apps
from max_gui.tools.overlay import ProjectedItem, project_and_draw, select_boxes
from max_gui.tools.paths import resolve_ocr_path
from max_gui.tools.protocol import Tool, ToolError, ToolResult

LOCATE_DESCRIPTION = (
    "对当前截图做可点击控件定位：返回最多 40 个编号、标签、视图像素中心，并回注带框图。"
    "点图标或按钮时优先调用，再用 mouse_move 的 target_id。"
    "可省略 path（默认最近一张截图）。仅当前截图的编号可用于 mouse_move；其他图仅供观察。"
    "可按 query 查询目标名称，region=dock 时优先使用 macOS Dock 的只读语义信息。"
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
        query = str(args.get("query") or "").strip()
        region = str(args.get("region") or "").strip().lower()
        semantic_status = "not_requested"
        if query and region == "dock" and executable and frame is not None:
            dock_boxes, semantic_status = _dock_boxes(
                query, frame=frame, width=width, height=height
            )
            if len(dock_boxes) == 1:
                boxes = dock_boxes
            elif dock_boxes:
                store_locate_hits({})
                return ToolResult(
                    text=json.dumps(
                        {"items": [], "semantic_status": "ambiguous", "observation_only": False},
                        ensure_ascii=False,
                    )
                )
        chosen = select_boxes(boxes, width=width, height=height)
        if query and not (region == "dock" and semantic_status == "ok"):
            chosen = _matching_boxes(chosen, query)
            semantic_status = (
                "matched" if len(chosen) == 1 else "not_matched" if not chosen else "ambiguous"
            )
            if len(chosen) != 1:
                store_locate_hits({})
                return ToolResult(
                    text=json.dumps(
                        {
                            "items": [],
                            "semantic_status": semantic_status,
                            "observation_only": not executable,
                        },
                        ensure_ascii=False,
                    )
                )
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
            "semantic_status": semantic_status,
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
                },
                "query": {"type": "string", "description": "要查找的控件或应用名称"},
                "region": {"type": "string", "enum": ["dock"], "description": "可选区域"},
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


def _matching_boxes(boxes: list[DetectedBox], query: str) -> list[DetectedBox]:
    """按名称及常见浏览器别名筛选，泛化 `icon` 永远不视为语义匹配。"""
    needle = _normalize_name(query)
    return [
        box for box in boxes if _normalize_name(box.label) == needle and box.label.lower() != "icon"
    ]


def _normalize_name(value: str) -> str:
    """统一少量常用 Dock 名称别名，避免把不确定 caption 当成命中。"""
    text = "".join(value.lower().split())
    aliases = {"googlechrome": "chrome", "谷歌浏览器": "chrome", "谷歌chrome": "chrome"}
    return aliases.get(text, text)


def _dock_boxes(
    query: str, *, frame: ViewFrame, width: int, height: int
) -> tuple[list[DetectedBox], str]:
    """把唯一 Dock 辅助功能候选投影回当前截图像素，保持其只读性质。"""
    candidates, status = find_dock_apps()
    matches = [item for item in candidates if _normalize_name(item.title) == _normalize_name(query)]
    if len(matches) != 1:
        return [], "ambiguous" if len(matches) > 1 else status
    item: DockCandidate = matches[0]
    if not (frame.origin_x <= item.x and frame.origin_y <= item.y):
        return [], "outside_current_frame"
    scale_x = width / frame.logical_width
    scale_y = height / frame.logical_height
    return [
        DetectedBox(
            x1=(item.x - frame.origin_x) * scale_x,
            y1=(item.y - frame.origin_y) * scale_y,
            x2=(item.x + item.width - frame.origin_x) * scale_x,
            y2=(item.y + item.height - frame.origin_y) * scale_y,
            label=item.title,
            role="icon",
            score=1.0,
        )
    ], "ok"
