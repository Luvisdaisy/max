"""桌面工具：截图回注、屏幕信息、移鼠、点按、拖拽、滚轮与键盘输入。

视图坐标系与 `ocr_locate` 命中表经 `restore_desktop_context` /
`snapshot_desktop_context` 与会话 JSON 同步，避免跨回合丢失。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from max_gui.config import Settings
from max_gui.desktop.backend import DesktopBackend, DesktopPermissionError
from max_gui.desktop.pyautogui_backend import ACCESSIBILITY_HELP, SCREEN_RECORDING_HELP
from max_gui.inference.images import prepare_image
from max_gui.tools.protocol import Tool, ToolError, ToolResult

current_session_id: ContextVar[str] = ContextVar("current_session_id", default="session")

KEY_ALIASES = {
    "escape": "esc",
    "return": "enter",
    "control": "ctrl",
    "option": "alt",
    "cmd": "command",
}
NAMED_KEYS = {
    "enter",
    "tab",
    "esc",
    "backspace",
    "space",
    "delete",
    "up",
    "down",
    "left",
    "right",
    "command",
    "shift",
    "ctrl",
    "alt",
}
DANGEROUS_HOTKEYS = {
    frozenset({"command", "q"}),
    frozenset({"command", "shift", "q"}),
    frozenset({"command", "alt", "esc"}),
}
FOREGROUND_HINT = (
    "输入会打到当前前台窗口，可能是终端本身。可先把目标窗口置于前台，或设置 delay_ms。"
)
VIEW_COORD_HINT = "坐标是你看到的最近一张截图上的像素，原点在图左上角。"


@dataclass(frozen=True, slots=True)
class ViewFrame:
    """最近一次成功截图的坐标系。

    字段：
        origin_x / origin_y: 区域左上角的逻辑坐标；全屏为 0。
        logical_width / logical_height: 该帧覆盖的逻辑宽高。
        view_width / view_height: 发给主模型的图像像素宽高。
        image_path: 落盘 PNG。
    """

    origin_x: int
    origin_y: int
    logical_width: int
    logical_height: int
    view_width: int
    view_height: int
    image_path: Path


current_view_frame: ContextVar[ViewFrame | None] = ContextVar("current_view_frame", default=None)
current_locate_hits: ContextVar[dict[int, tuple[int, int]] | None] = ContextVar(
    "current_locate_hits", default=None
)
_session_view_frames: dict[str, ViewFrame] = {}
_session_locate_hits: dict[str, dict[int, tuple[int, int]]] = {}


def _session_key() -> str:
    """当前会话编号；工具与 Agent 共用。"""
    return current_session_id.get()


def active_view_frame() -> ViewFrame | None:
    """优先 ContextVar，否则按会话编号取进程内缓存。"""
    return current_view_frame.get() or _session_view_frames.get(_session_key())


def active_locate_hits() -> dict[int, tuple[int, int]]:
    """优先 ContextVar，否则按会话编号取进程内缓存。"""
    hits = current_locate_hits.get()
    if hits:
        return hits
    return _session_locate_hits.get(_session_key()) or {}


def store_view_frame(frame: ViewFrame) -> None:
    """写入 ContextVar 与按会话缓存。"""
    current_view_frame.set(frame)
    _session_view_frames[_session_key()] = frame


def store_locate_hits(hits: dict[int, tuple[int, int]]) -> None:
    """写入 ContextVar 与按会话缓存。"""
    current_locate_hits.set(hits)
    _session_locate_hits[_session_key()] = hits


def clear_desktop_context() -> None:
    """清空当前会话的 ContextVar 与进程缓存，供测试冷启动。"""
    key = _session_key()
    current_view_frame.set(None)
    current_locate_hits.set(None)
    _session_view_frames.pop(key, None)
    _session_locate_hits.pop(key, None)


def view_frame_to_dict(frame: ViewFrame | None) -> dict[str, Any] | None:
    """把视图帧收成可写入会话 JSON 的字典。"""
    if frame is None:
        return None
    return {
        "origin_x": frame.origin_x,
        "origin_y": frame.origin_y,
        "logical_width": frame.logical_width,
        "logical_height": frame.logical_height,
        "view_width": frame.view_width,
        "view_height": frame.view_height,
        "image_path": str(frame.image_path),
    }


def view_frame_from_dict(data: dict[str, Any] | None) -> ViewFrame | None:
    """从会话 JSON 恢复视图帧；缺字段或非法值返回 `None`。"""
    if not data:
        return None
    try:
        return ViewFrame(
            origin_x=int(data["origin_x"]),
            origin_y=int(data["origin_y"]),
            logical_width=int(data["logical_width"]),
            logical_height=int(data["logical_height"]),
            view_width=int(data["view_width"]),
            view_height=int(data["view_height"]),
            image_path=Path(str(data.get("image_path") or "")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def locate_hits_to_dict(hits: dict[int, tuple[int, int]] | None) -> dict[str, list[int]]:
    """把定位编号表收成 JSON 对象。"""
    return {str(key): [int(point[0]), int(point[1])] for key, point in (hits or {}).items()}


def locate_hits_from_dict(data: Mapping[str, Any] | None) -> dict[int, tuple[int, int]]:
    """从会话 JSON 恢复定位编号表；坏项跳过。"""
    hits: dict[int, tuple[int, int]] = {}
    for key, value in (data or {}).items():
        try:
            if not isinstance(value, (list, tuple)) or len(value) < 2:
                continue
            hits[int(key)] = (int(value[0]), int(value[1]))
        except (TypeError, ValueError):
            continue
    return hits


def restore_desktop_context(
    view_frame: dict[str, Any] | None,
    locate_hits: Mapping[str, Any] | None,
) -> None:
    """用会话里保存的坐标系与定位表覆盖当前上下文与缓存。"""
    frame = view_frame_from_dict(view_frame)
    hits = locate_hits_from_dict(locate_hits)
    key = _session_key()
    current_view_frame.set(frame)
    current_locate_hits.set(hits or None)
    if frame is None:
        _session_view_frames.pop(key, None)
    else:
        _session_view_frames[key] = frame
    if hits:
        _session_locate_hits[key] = hits
    else:
        _session_locate_hits.pop(key, None)


def snapshot_desktop_context() -> tuple[dict[str, Any] | None, dict[str, list[int]]]:
    """取出当前坐标系与定位表，供写入会话。"""
    return view_frame_to_dict(active_view_frame()), locate_hits_to_dict(active_locate_hits())


def logical_to_view(
    x: int,
    y: int,
    *,
    origin_x: int,
    origin_y: int,
    logical_width: int,
    logical_height: int,
    view_width: int,
    view_height: int,
) -> tuple[int, int]:
    """把逻辑像素换成当前视图上的像素；逻辑尺寸非法时原样返回。"""
    if logical_width <= 0 or logical_height <= 0:
        return int(x), int(y)
    vx = round((int(x) - origin_x) * view_width / logical_width)
    vy = round((int(y) - origin_y) * view_height / logical_height)
    return vx, vy


def clamp_point(x: int, y: int, width: int, height: int) -> tuple[int, int, bool]:
    """把点夹到 `[0, width) × [0, height)`。返回 `(x, y, 是否发生夹紧)`。"""
    cx = min(max(0, int(x)), max(0, width - 1))
    cy = min(max(0, int(y)), max(0, height - 1))
    return cx, cy, cx != int(x) or cy != int(y)


def view_to_logical(
    x: int,
    y: int,
    frame: ViewFrame | None,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int, bool, bool]:
    """把视图像素换成逻辑像素并夹紧。

    参数：
        x / y: 模型给出的视图像素；无截图时当作逻辑像素。
        frame: 最近一次成功截图；`None` 表示尚未截图。
        screen_width / screen_height: 主屏逻辑尺寸。

    返回：
        `(逻辑 x, 逻辑 y, 是否做了视图换算, 是否夹紧)`。
    """
    if (
        frame is None
        or frame.view_width <= 0
        or frame.view_height <= 0
        or frame.logical_width <= 0
        or frame.logical_height <= 0
    ):
        lx, ly = int(x), int(y)
        used_view = False
    else:
        lx = frame.origin_x + round(int(x) * frame.logical_width / frame.view_width)
        ly = frame.origin_y + round(int(y) * frame.logical_height / frame.view_height)
        used_view = True
    cx, cy, clamped = clamp_point(lx, ly, screen_width, screen_height)
    return cx, cy, used_view, clamped


def lookup_locate_hit(target_id: int) -> tuple[int, int]:
    """按编号取最近一次 `ocr_locate` 的逻辑中心。

    异常：
        ToolError: 没有该编号。
    """
    hits = active_locate_hits()
    if target_id not in hits:
        raise ToolError(f"没有 id={target_id} 的定位结果，请先调用 ocr_locate")
    return hits[target_id]


def _coord_note(*, used_view: bool, used_id: bool, clamped: bool) -> str:
    """拼坐标来源说明。"""
    parts: list[str] = []
    if used_id:
        parts.append("按定位编号")
    elif used_view:
        parts.append("已从视图像素换算")
    else:
        parts.append("尚无截图，按逻辑像素")
    if clamped:
        parts.append("已夹紧到屏幕内")
    return "（" + "；".join(parts) + "）"


def _is_black_or_tiny(image: Image.Image) -> bool:
    """过小或几乎全黑，视为未授予屏幕录制权限。"""
    width, height = image.size
    if width < 8 or height < 8:
        return True
    extrema = image.convert("L").getextrema()
    return extrema is not None and extrema[1] <= 8


def _draw_cursor(image: Image.Image, x: int, y: int, scale: float) -> None:
    """在截图像素坐标上画红色十字，逻辑坐标需乘 `scale`。"""
    px = int(x * scale)
    py = int(y * scale)
    draw = ImageDraw.Draw(image)
    size = max(8, int(12 * max(scale, 1.0)))
    draw.line((px - size, py, px + size, py), fill=(255, 48, 48), width=2)
    draw.line((px, py - size, px, py + size), fill=(255, 48, 48), width=2)


def _normalize_key(raw: str) -> str:
    """小写并映射别名，如 `return` → `enter`、`cmd` → `command`。"""
    key = raw.strip().lower()
    return KEY_ALIASES.get(key, key)


def _allowed_key(key: str) -> bool:
    """是否在命名键或单字符白名单内。"""
    if key in NAMED_KEYS:
        return True
    return len(key) == 1 and (key.isalnum() or key in {".", ",", "-", "=", "[", "]"})


def _parse_keys(raw: Any) -> list[str]:
    """解析 `keys` 字符串或列表，拒绝未知键与危险热键。"""
    if raw is None:
        raise ToolError("keyboard_press 需要 keys")
    if isinstance(raw, str):
        parts = [item for item in raw.replace("+", " ").split() if item]
    elif isinstance(raw, list):
        parts = [str(item) for item in raw]
    else:
        raise ToolError("keys 必须是字符串或字符串数组")
    keys = [_normalize_key(item) for item in parts]
    if not keys:
        raise ToolError("keys 不能为空")
    unknown = [key for key in keys if not _allowed_key(key)]
    if unknown:
        raise ToolError(f"拒绝未知键名：{', '.join(unknown)}")
    if frozenset(keys) in DANGEROUS_HOTKEYS:
        raise ToolError(f"拒绝危险热键：{'+'.join(keys)}")
    return keys


def desktop_tools(settings: Settings, backend: DesktopBackend) -> list[Tool]:
    """构造桌面工具。点击、拖拽、滚动与键盘的确认范围为 `desktop`。

    参数：
        settings: 提供截图目录与图像上限。
        backend: 真实或测试后端。
    """
    screenshots_dir = Path(settings.screenshots_dir)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    async def _call(fn, *args, **kwargs):
        """在线程中跑同步后端，权限错误转成 `ToolError`。"""
        try:
            return await asyncio.to_thread(fn, *args, **kwargs)
        except DesktopPermissionError as exc:
            raise ToolError(
                str(exc)
                if str(exc).startswith("截图失败") or str(exc).startswith("键鼠")
                else (
                    SCREEN_RECORDING_HELP if exc.kind == "screen_recording" else ACCESSIBILITY_HELP
                )
            ) from exc

    async def _resolve_point(
        args: dict,
        width: int,
        height: int,
        *,
        x_key: str = "x",
        y_key: str = "y",
        require: bool = False,
    ) -> tuple[int, int, bool, bool] | None:
        """从 `target_id` 或视图像素解析一个逻辑点。"""
        if args.get("target_id") is not None:
            hit = lookup_locate_hit(int(args["target_id"]))
            cx, cy, clamped = clamp_point(hit[0], hit[1], width, height)
            return cx, cy, False, clamped
        if args.get(x_key) is None or args.get(y_key) is None:
            if require:
                raise ToolError(f"需要 {x_key}/{y_key} 或 target_id")
            return None
        return view_to_logical(
            int(args.get(x_key) or 0),
            int(args.get(y_key) or 0),
            active_view_frame(),
            width,
            height,
        )

    async def screen_info(_args: dict) -> str:
        """返回逻辑分辨率、scale 与鼠标坐标的 JSON。"""
        width, height = await _call(backend.size)
        mouse_x, mouse_y = await _call(backend.position)
        shot = await _call(backend.screenshot)
        scale = shot.width / width if width else 1.0
        if _is_black_or_tiny(shot):
            raise ToolError(SCREEN_RECORDING_HELP)
        return json.dumps(
            {
                "screen_width": width,
                "screen_height": height,
                "scale": scale,
                "mouse_x": mouse_x,
                "mouse_y": mouse_y,
                "coordinate_space": "logical",
            },
            ensure_ascii=False,
        )

    async def screenshot(args: dict) -> ToolResult:
        """截主屏或 `region`，落盘 PNG 并把图像回注给模型。"""
        width, height = await _call(backend.size)
        mouse_x, mouse_y = await _call(backend.position)
        region = args.get("region")
        region_tuple = None
        if isinstance(region, dict):
            region_tuple = (
                int(region.get("x") or 0),
                int(region.get("y") or 0),
                int(region.get("width") or width),
                int(region.get("height") or height),
            )
        image = await _call(backend.screenshot, region_tuple)
        if _is_black_or_tiny(image):
            raise ToolError(SCREEN_RECORDING_HELP)
        logical_w = region_tuple[2] if region_tuple else width
        logical_h = region_tuple[3] if region_tuple else height
        scale = image.width / logical_w if logical_w else 1.0
        show_cursor = args.get("show_cursor", True)
        if show_cursor is not False:
            cursor_x, cursor_y = mouse_x, mouse_y
            if region_tuple:
                cursor_x -= region_tuple[0]
                cursor_y -= region_tuple[1]
            _draw_cursor(image, cursor_x, cursor_y, scale)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = screenshots_dir / f"{current_session_id.get()}-{stamp}.png"
        image.save(path)
        prepared = prepare_image(
            path, max_edge=settings.max_image_edge, max_bytes=settings.max_image_bytes
        )
        origin_x = region_tuple[0] if region_tuple else 0
        origin_y = region_tuple[1] if region_tuple else 0
        store_view_frame(
            ViewFrame(
                origin_x=origin_x,
                origin_y=origin_y,
                logical_width=logical_w,
                logical_height=logical_h,
                view_width=prepared.width,
                view_height=prepared.height,
                image_path=path,
            )
        )
        cursor_vx, cursor_vy = logical_to_view(
            mouse_x,
            mouse_y,
            origin_x=origin_x,
            origin_y=origin_y,
            logical_width=logical_w,
            logical_height=logical_h,
            view_width=prepared.width,
            view_height=prepared.height,
        )
        summary = json.dumps(
            {
                "path": str(path),
                "width": logical_w,
                "height": logical_h,
                "view_width": prepared.width,
                "view_height": prepared.height,
                "origin": {"x": origin_x, "y": origin_y},
                "scale": scale,
                "cursor": {"x": cursor_vx, "y": cursor_vy},
                "coordinate_space": "view",
            },
            ensure_ascii=False,
        )
        return ToolResult(text=summary, images=[path])

    async def mouse_move(args: dict) -> str:
        """移到视图像素对应的逻辑坐标，或按定位编号。"""
        width, height = await _call(backend.size)
        resolved = await _resolve_point(args, width, height, require=True)
        assert resolved is not None
        x, y, used_view, clamped = resolved
        used_id = args.get("target_id") is not None
        duration = float(args.get("duration") if args.get("duration") is not None else 0.2)
        await _call(backend.move_to, x, y, duration)
        return f"指针已移到逻辑坐标 ({x}, {y}){_coord_note(used_view=used_view, used_id=used_id, clamped=clamped)}"

    async def mouse_click(args: dict) -> str:
        """单击或双击；可先按视图像素或定位编号移动。"""
        width, height = await _call(backend.size)
        button = str(args.get("button") or "left")
        clicks = int(args.get("clicks") or 1)
        duration = float(args.get("duration") if args.get("duration") is not None else 0.2)
        resolved = await _resolve_point(args, width, height, require=False)
        used_id = args.get("target_id") is not None
        used_view = False
        clamped = False
        target_x = target_y = None
        if resolved is not None:
            target_x, target_y, used_view, clamped = resolved
        await _call(
            backend.click, button=button, clicks=clicks, x=target_x, y=target_y, duration=duration
        )
        where = f"({target_x}, {target_y})" if target_x is not None else "当前位置"
        note = (
            _coord_note(used_view=used_view, used_id=used_id, clamped=clamped)
            if target_x is not None
            else ""
        )
        return f"已{('双击' if clicks == 2 else '单击')}{button} {where}{note}"

    async def mouse_drag(args: dict) -> str:
        """从视图像素 `(x1, y1)` 拖到 `(x2, y2)`。"""
        width, height = await _call(backend.size)
        start = await _resolve_point(args, width, height, x_key="x1", y_key="y1", require=True)
        end = await _resolve_point(args, width, height, x_key="x2", y_key="y2", require=True)
        assert start is not None and end is not None
        x1, y1, v1, c1 = start
        x2, y2, v2, c2 = end
        duration = float(args.get("duration") if args.get("duration") is not None else 0.2)
        button = str(args.get("button") or "left")
        await _call(backend.drag_to, x1, y1, x2, y2, duration=duration, button=button)
        note = _coord_note(used_view=v1 or v2, used_id=False, clamped=c1 or c2)
        return f"已从 ({x1}, {y1}) 拖到 ({x2}, {y2}){note}"

    async def mouse_scroll(args: dict) -> str:
        """按视图像素可选先移动，再滚动。"""
        clicks = args.get("clicks")
        if clicks is None:
            raise ToolError("mouse_scroll 需要 clicks")
        width, height = await _call(backend.size)
        resolved = await _resolve_point(args, width, height, require=False)
        used_id = args.get("target_id") is not None
        x = y = None
        used_view = False
        clamped = False
        if resolved is not None:
            x, y, used_view, clamped = resolved
        await _call(backend.scroll, int(clicks), x, y)
        where = f"在 ({x}, {y}) " if x is not None else ""
        direction = "向上" if int(clicks) > 0 else "向下" if int(clicks) < 0 else ""
        note = (
            _coord_note(used_view=used_view, used_id=used_id, clamped=clamped)
            if x is not None
            else ""
        )
        return f"已{where}{direction}滚动 {abs(int(clicks))} 格{note}"

    async def keyboard_type(args: dict) -> str:
        """ASCII 走 `write`，非 ASCII 走剪贴板粘贴。"""
        text = str(args.get("text") or "")
        if not text:
            raise ToolError("keyboard_type 需要 text")
        interval = float(args.get("interval") or 0)
        delay_ms = int(args.get("delay_ms") or 0)
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)
        if any(ord(char) > 127 for char in text):
            await _call(backend.paste, text)
            method = "剪贴板粘贴"
        else:
            await _call(backend.write, text, interval)
            method = "write"
        return f"已用{method}输入 {len(text)} 个字符。{FOREGROUND_HINT}"

    async def keyboard_press(args: dict) -> str:
        """按白名单单键或组合键。"""
        keys = _parse_keys(args.get("keys"))
        interval = float(args.get("interval") or 0)
        delay_ms = int(args.get("delay_ms") or 0)
        if delay_ms > 0:
            await asyncio.sleep(delay_ms / 1000)
        if len(keys) == 1:
            await _call(backend.press, keys[0])
        else:
            await _call(backend.hotkey, *keys)
            if interval:
                await asyncio.sleep(interval)
        return f"已按下 {'+'.join(keys)}。{FOREGROUND_HINT}"

    return [
        Tool(
            name="screenshot",
            description=(
                "截取主屏或指定逻辑像素区域，返回摘要并把图像回注给模型。"
                "随后的鼠标坐标请使用这张图上的视图像素，不要用逻辑分辨率或 0-1000。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "region": {
                        "type": "object",
                        "description": "逻辑像素区域，原点在主屏左上角，不是视图像素",
                        "properties": {
                            "x": {"type": "integer", "description": "逻辑像素 x"},
                            "y": {"type": "integer", "description": "逻辑像素 y"},
                            "width": {"type": "integer", "description": "逻辑像素宽"},
                            "height": {"type": "integer", "description": "逻辑像素高"},
                        },
                    },
                    "show_cursor": {
                        "type": "boolean",
                        "description": "是否在图上标注光标，默认 true",
                    },
                },
            },
            invoke=screenshot,
        ),
        Tool(
            name="screen_info",
            description="返回主屏逻辑分辨率、scale 与当前鼠标逻辑坐标",
            parameters={"type": "object", "properties": {}},
            invoke=screen_info,
        ),
        Tool(
            name="mouse_move",
            description=f"将指针移到视图像素 (x, y)，或按 ocr_locate 的 target_id。{VIEW_COORD_HINT}",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "target_id": {"type": "integer", "description": "ocr_locate 返回的编号"},
                    "duration": {"type": "number"},
                },
            },
            invoke=mouse_move,
        ),
        Tool(
            name="mouse_click",
            description=(
                f"单击或双击。可先移到视图像素或 ocr_locate 的 target_id。{VIEW_COORD_HINT}"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                    "clicks": {"type": "integer", "enum": [1, 2]},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "target_id": {"type": "integer"},
                    "duration": {"type": "number"},
                },
            },
            invoke=mouse_click,
            confirmation_scope="desktop",
        ),
        Tool(
            name="mouse_drag",
            description=f"从视图像素 (x1, y1) 拖到 (x2, y2)。{VIEW_COORD_HINT}",
            parameters={
                "type": "object",
                "properties": {
                    "x1": {"type": "integer"},
                    "y1": {"type": "integer"},
                    "x2": {"type": "integer"},
                    "y2": {"type": "integer"},
                    "duration": {"type": "number"},
                    "button": {"type": "string"},
                },
                "required": ["x1", "y1", "x2", "y2"],
            },
            invoke=mouse_drag,
            confirmation_scope="desktop",
        ),
        Tool(
            name="mouse_scroll",
            description=f"滚动滚轮。clicks 正数向上。可选先移到视图像素。{VIEW_COORD_HINT}",
            parameters={
                "type": "object",
                "properties": {
                    "clicks": {"type": "integer"},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "target_id": {"type": "integer"},
                },
                "required": ["clicks"],
            },
            invoke=mouse_scroll,
            confirmation_scope="desktop",
        ),
        Tool(
            name="keyboard_type",
            description="向当前焦点输入文本。ASCII 模拟按键；非 ASCII 会覆盖剪贴板并粘贴。不要传按键名。",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "interval": {"type": "number"},
                    "delay_ms": {"type": "integer"},
                },
                "required": ["text"],
            },
            invoke=keyboard_type,
            confirmation_scope="desktop",
        ),
        Tool(
            name="keyboard_press",
            description="按下白名单中的单个键或组合键，例如 enter 或 [command, space]。不要传自由文本。",
            parameters={
                "type": "object",
                "properties": {
                    "keys": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ]
                    },
                    "interval": {"type": "number"},
                    "delay_ms": {"type": "integer"},
                },
                "required": ["keys"],
            },
            invoke=keyboard_press,
            confirmation_scope="desktop",
        ),
    ]
