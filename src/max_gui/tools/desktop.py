from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from max_gui.config import Settings
from max_gui.desktop.backend import DesktopBackend, DesktopPermissionError
from max_gui.desktop.pyautogui_backend import ACCESSIBILITY_HELP, SCREEN_RECORDING_HELP
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


def clamp_point(x: int, y: int, width: int, height: int) -> tuple[int, int, bool]:
    cx = min(max(0, int(x)), max(0, width - 1))
    cy = min(max(0, int(y)), max(0, height - 1))
    return cx, cy, cx != int(x) or cy != int(y)


def _is_black_or_tiny(image: Image.Image) -> bool:
    width, height = image.size
    if width < 8 or height < 8:
        return True
    extrema = image.convert("L").getextrema()
    return extrema is not None and extrema[1] <= 8


def _draw_cursor(image: Image.Image, x: int, y: int, scale: float) -> None:
    px = int(x * scale)
    py = int(y * scale)
    draw = ImageDraw.Draw(image)
    size = max(8, int(12 * max(scale, 1.0)))
    draw.line((px - size, py, px + size, py), fill=(255, 48, 48), width=2)
    draw.line((px, py - size, px, py + size), fill=(255, 48, 48), width=2)


def _normalize_key(raw: str) -> str:
    key = raw.strip().lower()
    return KEY_ALIASES.get(key, key)


def _allowed_key(key: str) -> bool:
    if key in NAMED_KEYS:
        return True
    return len(key) == 1 and (key.isalnum() or key in {".", ",", "-", "=", "[", "]"})


def _parse_keys(raw: Any) -> list[str]:
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
    screenshots_dir = Path(settings.screenshots_dir)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    async def _call(fn, *args, **kwargs):
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

    async def screen_info(_args: dict) -> str:
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
        scale = image.width / (region_tuple[2] if region_tuple else width)
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
        summary = json.dumps(
            {
                "path": str(path),
                "width": region_tuple[2] if region_tuple else width,
                "height": region_tuple[3] if region_tuple else height,
                "scale": scale,
                "cursor": {"x": mouse_x, "y": mouse_y},
                "coordinate_space": "logical",
            },
            ensure_ascii=False,
        )
        return ToolResult(text=summary, images=[path])

    async def mouse_move(args: dict) -> str:
        width, height = await _call(backend.size)
        x, y, clamped = clamp_point(int(args.get("x") or 0), int(args.get("y") or 0), width, height)
        duration = float(args.get("duration") if args.get("duration") is not None else 0.2)
        await _call(backend.move_to, x, y, duration)
        note = "（已夹紧到屏幕内）" if clamped else ""
        return f"指针已移到逻辑坐标 ({x}, {y}){note}"

    async def mouse_click(args: dict) -> str:
        width, height = await _call(backend.size)
        button = str(args.get("button") or "left")
        clicks = int(args.get("clicks") or 1)
        duration = float(args.get("duration") if args.get("duration") is not None else 0.2)
        x = args.get("x")
        y = args.get("y")
        clamped = False
        target_x = target_y = None
        if x is not None and y is not None:
            target_x, target_y, clamped = clamp_point(int(x), int(y), width, height)
        await _call(
            backend.click, button=button, clicks=clicks, x=target_x, y=target_y, duration=duration
        )
        where = f"({target_x}, {target_y})" if target_x is not None else "当前位置"
        note = "（已夹紧到屏幕内）" if clamped else ""
        return f"已{('双击' if clicks == 2 else '单击')}{button} {where}{note}"

    async def mouse_drag(args: dict) -> str:
        width, height = await _call(backend.size)
        x1, y1, c1 = clamp_point(int(args.get("x1") or 0), int(args.get("y1") or 0), width, height)
        x2, y2, c2 = clamp_point(int(args.get("x2") or 0), int(args.get("y2") or 0), width, height)
        duration = float(args.get("duration") if args.get("duration") is not None else 0.2)
        button = str(args.get("button") or "left")
        await _call(backend.drag_to, x1, y1, x2, y2, duration=duration, button=button)
        note = "（已夹紧到屏幕内）" if c1 or c2 else ""
        return f"已从 ({x1}, {y1}) 拖到 ({x2}, {y2}){note}"

    async def keyboard_type(args: dict) -> str:
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
            description="截取主屏或指定逻辑像素区域，返回摘要并把图像回注给模型。坐标使用逻辑像素。",
            parameters={
                "type": "object",
                "properties": {
                    "region": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer"},
                            "y": {"type": "integer"},
                            "width": {"type": "integer"},
                            "height": {"type": "integer"},
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
            description="将指针移到逻辑坐标 (x, y)",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "duration": {"type": "number"},
                },
                "required": ["x", "y"],
            },
            invoke=mouse_move,
        ),
        Tool(
            name="mouse_click",
            description="单击或双击。可先移动到逻辑坐标。会点击当前前台窗口。",
            parameters={
                "type": "object",
                "properties": {
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                    "clicks": {"type": "integer", "enum": [1, 2]},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "duration": {"type": "number"},
                },
            },
            invoke=mouse_click,
            confirmation_scope="desktop",
        ),
        Tool(
            name="mouse_drag",
            description="从逻辑坐标 (x1, y1) 拖到 (x2, y2)",
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
