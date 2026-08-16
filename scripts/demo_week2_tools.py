"""第二周桌面感知与控制演示：打开 macOS 计算器，用现有工具走完截图、键鼠、画框与 OCR。

运行：``uv run python scripts/demo_week2_tools.py``

约束：仅 macOS；需屏幕录制与辅助功能权限。产物写入 ``artifacts/week2-demo/``。
首次 OCR 会在本脚本里预热独立 PaddleOCR-VL（约 1–3 分钟），避免点到 ``ocr`` 时才启动又被跳过。
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from max_gui.config import MissingVllmError, Settings, load_settings, weights_ready
from max_gui.inference.ocr import OcrRuntime, OcrUnavailable, ocr_serve_command
from max_gui.lifecycle import resolve_vllm_bin
from max_gui.tools.desktop import active_view_frame, current_session_id, logical_to_view
from max_gui.tools.protocol import ToolResult
from max_gui.tools.registry import AutoApproveGate, ToolRegistry, build_default_registry

PROCESS_NAMES = ("Calculator", "计算器")
COUNTDOWN_SECONDS = 3
WINDOW_WAIT_SECONDS = 12
CLICK_PAUSE = 0.18
DISPLAY_RATIO = 0.326
TITLE_H = 52
SIDEBAR_MIN_WIDTH = 360
SIDEBAR_RATIO = 0.498
KEYPAD_PAD = 10
KEYPAD_GAP = 6
DRAG_OFFSET = (120, 80)
HISTORY_MENUS = (
    ("View", "Show History"),
    ("View", "Show Paper Tape"),
    ("显示", "显示历史记录"),
    ("显示", "显示纸带"),
)
KEYPAD_ROWS = (
    ("backspace", "AC", "%", "÷"),
    ("7", "8", "9", "×"),
    ("4", "5", "6", "−"),
    ("1", "2", "3", "+"),
    ("+/-", "0", ".", "="),
)
BUTTON_ORDER = tuple(name for row in KEYPAD_ROWS for name in row)
BOX_NAMES = ("history", "scrollbar", "drag", "display", *BUTTON_ORDER)


@dataclass(frozen=True, slots=True)
class Rect:
    """轴对齐矩形，坐标为屏幕逻辑像素。

    字段：
        name: 区域名。
        x / y: 左上角。
        w / h: 宽高。
    """

    name: str
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> int:
        """水平中心。"""
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        """垂直中心。"""
        return self.y + self.h // 2


@dataclass(frozen=True, slots=True)
class WindowBox:
    """计算器窗口的逻辑像素外框。"""

    x: int
    y: int
    w: int
    h: int

    @property
    def has_sidebar(self) -> bool:
        """宽度达到阈值则视为已展开左侧历史栏。"""
        return self.w >= SIDEBAR_MIN_WIDTH

    @property
    def region(self) -> dict[str, int]:
        """``screenshot`` 的 ``region`` 参数。"""
        return {"x": self.x, "y": self.y, "width": self.w, "height": self.h}


def calculator_layout(
    window: WindowBox, *, controls: dict[str, Rect] | None = None
) -> dict[str, Rect]:
    """推计算器各区域。优先用辅助功能读到的真实按钮框，否则按实测网格估算。

    参数：
        window: 窗口外框。
        controls: ``read_ax_layout`` 的结果；缺省或不全时用几何回退。

    返回：
        显示区、拖拽空白、可选历史栏与 20 个按键矩形。
    """
    layout = _geometric_layout(window)
    if controls:
        layout.update(controls)
    return layout


def _clamp_rect(window: WindowBox, name: str, x: int, y: int, w: int, h: int) -> Rect:
    """把矩形夹进窗口内，避免 1px 舍入越界。"""
    left = max(window.x, x)
    top = max(window.y, y)
    right = min(window.x + window.w, x + max(1, w))
    bottom = min(window.y + window.h, y + max(1, h))
    return Rect(name, left, top, max(1, right - left), max(1, bottom - top))


def _geometric_layout(window: WindowBox) -> dict[str, Rect]:
    """按 Sequoia 计算器实测：侧栏约一半，按键 48px、间距 6、左右各留 10。"""
    sidebar_w = round(window.w * SIDEBAR_RATIO) if window.has_sidebar else 0
    keypad_x = window.x + sidebar_w
    keypad_w = max(1, window.w - sidebar_w)
    keypad_top = window.y + round(window.h * DISPLAY_RATIO)
    inner_x = keypad_x + KEYPAD_PAD
    inner_w = max(1, keypad_w - 2 * KEYPAD_PAD)
    inner_h = max(1, window.y + window.h - keypad_top - KEYPAD_PAD)
    cell_w = (inner_w - 3 * KEYPAD_GAP) / 4
    cell_h = (inner_h - 4 * KEYPAD_GAP) / 5
    layout: dict[str, Rect] = {}
    if sidebar_w:
        layout["sidebar"] = _clamp_rect(window, "sidebar", window.x, window.y, sidebar_w, window.h)
        layout["history"] = _clamp_rect(
            window,
            "history",
            window.x + 8,
            window.y + TITLE_H,
            sidebar_w - 16,
            window.h - TITLE_H - 12,
        )
        layout["scrollbar"] = _clamp_rect(
            window,
            "scrollbar",
            keypad_x - 16,
            window.y + TITLE_H + 8,
            14,
            window.h - TITLE_H - 24,
        )
    layout["drag"] = _clamp_rect(
        window, "drag", inner_x, window.y + 6, max(48, inner_w // 2), TITLE_H - 12
    )
    layout["display"] = _clamp_rect(
        window,
        "display",
        inner_x,
        window.y + TITLE_H,
        inner_w,
        max(1, keypad_top - window.y - TITLE_H),
    )
    for row_index, row in enumerate(KEYPAD_ROWS):
        for col_index, name in enumerate(row):
            layout[name] = _clamp_rect(
                window,
                name,
                inner_x + round(col_index * (cell_w + KEYPAD_GAP)),
                keypad_top + round(row_index * (cell_h + KEYPAD_GAP)),
                round(cell_w),
                round(cell_h),
            )
    return layout


def parse_ax_report(text: str) -> dict[str, Rect]:
    """解析 ``read_ax_layout`` 的行协议。空输入返回空表。"""
    layout: dict[str, Rect] = {}
    toolbar: list[Rect] = []
    for raw in text.splitlines():
        parts = raw.strip().split("|")
        if len(parts) < 5:
            continue
        kind, xs, ys, ws, hs = parts[0], parts[1], parts[2], parts[3], parts[4]
        try:
            box = Rect(kind.lower(), int(xs), int(ys), int(ws), int(hs))
        except ValueError:
            continue
        if kind == "BTN" and len(parts) >= 6:
            try:
                index = int(parts[5])
            except ValueError:
                continue
            if 1 <= index <= len(BUTTON_ORDER):
                name = BUTTON_ORDER[index - 1]
                layout[name] = Rect(name, box.x, box.y, box.w, box.h)
        elif kind == "TB":
            toolbar.append(box)
        elif kind in {"HIST", "SCROLL", "DISPLAY", "SIDEBAR", "DRAG"}:
            names = {
                "HIST": "history",
                "SCROLL": "scrollbar",
                "DISPLAY": "display",
                "SIDEBAR": "sidebar",
                "DRAG": "drag",
            }
            name = names[kind]
            layout[name] = Rect(name, box.x, box.y, box.w, box.h)
    if "drag" not in layout and len(toolbar) >= 2:
        left, right = toolbar[0], toolbar[-1]
        x = left.x + left.w + 8
        w = right.x - x - 8
        if w >= 40:
            layout["drag"] = Rect("drag", x, left.y + 6, w, max(16, left.h - 12))
    return layout


def read_ax_layout() -> dict[str, Rect]:
    """用辅助功能读取历史栏、显示区与 20 个按键的真实逻辑像素框。

    返回：
        读到的矩形；失败或不足 20 个按键时返回空表，由几何回退接手。
    """
    script = r"""
tell application "System Events"
    tell process "Calculator"
        set win to window 1
        set out to ""
        set keypad to missing value
        try
            set keypad to group 1 of group 2 of splitter group 1 of group 1 of win
        end try
        if keypad is missing value then
            try
                set keypad to group 1 of group 1 of win
            end try
        end if
        if keypad is missing value then return ""
        set i to 1
        repeat with b in buttons of keypad
            set p to position of b
            set s to size of b
            set out to out & "BTN|" & (item 1 of p) & "|" & (item 2 of p) & "|" & (item 1 of s) & "|" & (item 2 of s) & "|" & i & linefeed
            set i to i + 1
        end repeat
        try
            set hist to scroll area 1 of group 1 of splitter group 1 of group 1 of win
            set p to position of hist
            set s to size of hist
            set out to out & "HIST|" & (item 1 of p) & "|" & (item 2 of p) & "|" & (item 1 of s) & "|" & (item 2 of s) & linefeed
            set sb to scroll bar 1 of hist
            set p to position of sb
            set s to size of sb
            set out to out & "SCROLL|" & (item 1 of p) & "|" & (item 2 of p) & "|" & (item 1 of s) & "|" & (item 2 of s) & linefeed
        end try
        try
            set leftg to group 1 of splitter group 1 of group 1 of win
            set p to position of leftg
            set s to size of leftg
            set out to out & "SIDEBAR|" & (item 1 of p) & "|" & (item 2 of p) & "|" & (item 1 of s) & "|" & (item 2 of s) & linefeed
        end try
        try
            set expr to scroll area 1 of keypad
            set val to scroll area 2 of keypad
            set p to position of expr
            set s2 to size of val
            set p2 to position of val
            set out to out & "DISPLAY|" & (item 1 of p) & "|" & (item 2 of p) & "|" & (item 1 of s2) & "|" & ((item 2 of p2) + (item 2 of s2) - (item 2 of p)) & linefeed
        end try
        try
            repeat with b in buttons of toolbar 1 of win
                set p to position of b
                set s to size of b
                set out to out & "TB|" & (item 1 of p) & "|" & (item 2 of p) & "|" & (item 1 of s) & "|" & (item 2 of s) & linefeed
            end repeat
        end try
        return out
    end tell
end tell
"""
    result = _osascript(script)
    if result.returncode != 0:
        return {}
    layout = parse_ax_report(result.stdout)
    if sum(1 for name in BUTTON_ORDER if name in layout) < len(BUTTON_ORDER):
        return {}
    return layout


def _osascript(source: str) -> subprocess.CompletedProcess[str]:
    """执行一段 AppleScript，不抛异常。长脚本走标准输入。"""
    return subprocess.run(
        ["osascript", "-"],
        input=source,
        capture_output=True,
        text=True,
        check=False,
    )


def open_calculator() -> None:
    """用 ``open -a`` 拉起计算器。

    异常：
        RuntimeError: 英文名与中文名都打不开。
    """
    for name in PROCESS_NAMES:
        result = subprocess.run(["open", "-a", name], capture_output=True, text=True, check=False)
        if result.returncode == 0:
            return
    raise RuntimeError("无法打开计算器。请确认本机已安装「计算器」应用。")


def _switch_to_basic(process_name: str) -> None:
    """尽量切到基础模式，避免科学计算器布局对不齐。"""
    script = f'''
    tell application "System Events"
        if not (exists process "{process_name}") then return
        tell process "{process_name}"
            set frontmost to true
            try
                click menu item "Basic" of menu "View" of menu bar 1
            end try
            try
                click menu item "基本" of menu "显示" of menu bar 1
            end try
        end tell
    end tell
    '''
    _osascript(script)


def _show_history_menu(process_name: str) -> None:
    """通过菜单展开历史栏，菜单名不存在则忽略。"""
    for menu, item in HISTORY_MENUS:
        script = f'''
        tell application "System Events"
            if not (exists process "{process_name}") then return
            tell process "{process_name}"
                set frontmost to true
                try
                    click menu item "{item}" of menu "{menu}" of menu bar 1
                end try
            end tell
        end tell
        '''
        _osascript(script)


def read_calculator_window() -> WindowBox:
    """从 System Events 读取前台计算器窗口的位置与尺寸。

    异常：
        RuntimeError: 进程不存在、没有窗口或输出无法解析。
    """
    errors: list[str] = []
    for name in PROCESS_NAMES:
        script = f'''
        tell application "System Events"
            if not (exists process "{name}") then error "没有进程 {name}"
            tell process "{name}"
                set frontmost to true
                set p to position of window 1
                set s to size of window 1
                return (item 1 of p as text) & "," & (item 2 of p as text) & "," & ¬
                    (item 1 of s as text) & "," & (item 2 of s as text)
            end tell
        end tell
        '''
        result = _osascript(script)
        if result.returncode == 0:
            parts = [item.strip() for item in result.stdout.strip().split(",")]
            if len(parts) != 4:
                errors.append(f"{name}: {result.stdout.strip()}")
                continue
            try:
                x, y, width, height = (int(float(item)) for item in parts)
            except ValueError:
                errors.append(f"{name}: {result.stdout.strip()}")
                continue
            if width < 80 or height < 80:
                errors.append(f"{name}: 窗口过小 {width}x{height}")
                continue
            return WindowBox(x, y, width, height)
        errors.append(f"{name}: {(result.stderr or result.stdout).strip()}")
    detail = "；".join(item for item in errors if item) or "未知错误"
    raise RuntimeError(
        "读不到计算器窗口。"
        "请打开 系统设置 → 隐私与安全性 → 辅助功能，勾选运行本脚本的终端后重试。"
        f"详情：{detail}"
    )


def wait_for_calculator_window(*, timeout: float = WINDOW_WAIT_SECONDS) -> WindowBox:
    """打开后轮询窗口矩形，直到可读或超时。

    异常：
        RuntimeError: 超时仍没有可用窗口。
    """
    deadline = time.monotonic() + timeout
    last_error = "尚未开始"
    while time.monotonic() < deadline:
        for name in PROCESS_NAMES:
            _switch_to_basic(name)
        try:
            return read_calculator_window()
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"等待计算器窗口超时（{timeout:.0f}s）。{last_error}")


def ensure_history_sidebar() -> WindowBox:
    """展开左侧历史栏并返回最新窗口矩形。

    先点菜单；仍是窄窗口时再点紧凑标题栏上的历史按钮。
    """
    window = read_calculator_window()
    if window.has_sidebar:
        return window
    for name in PROCESS_NAMES:
        _show_history_menu(name)
    time.sleep(0.4)
    window = read_calculator_window()
    if window.has_sidebar:
        return window
    return window


def _result_text(result: str | ToolResult) -> str:
    """取出工具返回的文本。"""
    return result.text if isinstance(result, ToolResult) else str(result)


def _screenshot_path(result: str | ToolResult) -> Path | None:
    """从截图结果里取落盘路径。"""
    if isinstance(result, ToolResult) and result.images:
        return result.images[0]
    try:
        payload = json.loads(_result_text(result))
    except json.JSONDecodeError:
        return None
    raw = payload.get("path")
    return Path(raw) if raw else None


def _view_point(x: int, y: int) -> tuple[int, int]:
    """把逻辑点换成当前截图上的视图像素；尚无视图帧则原样返回。"""
    frame = active_view_frame()
    if frame is None:
        return x, y
    return logical_to_view(
        x,
        y,
        origin_x=frame.origin_x,
        origin_y=frame.origin_y,
        logical_width=frame.logical_width,
        logical_height=frame.logical_height,
        view_width=frame.view_width,
        view_height=frame.view_height,
    )


def draw_layout_boxes(source: Path, layout: dict[str, Rect], window: WindowBox, dest: Path) -> None:
    """在区域截图上画编号框，样式接近 ``ocr_locate``。

    参数：
        source: 计算器区域截图。
        layout: ``calculator_layout`` 的结果。
        window: 该截图对应的窗口外框。
        dest: 输出 PNG。
    """
    with Image.open(source) as image:
        overlay = image.convert("RGB")
    scale_x = overlay.width / window.w if window.w else 1.0
    scale_y = overlay.height / window.h if window.h else 1.0
    draw = ImageDraw.Draw(overlay)
    font = ImageFont.load_default()
    index = 1
    for name in BOX_NAMES:
        box = layout.get(name)
        if box is None:
            continue
        left = (box.x - window.x) * scale_x
        top = (box.y - window.y) * scale_y
        right = left + box.w * scale_x
        bottom = top + box.h * scale_y
        draw.rectangle((left, top, right, bottom), outline=(255, 220, 40), width=2)
        label = f"{index}:{name}"
        tx, ty = int(left) + 2, max(0, int(top) + 2)
        draw.rectangle((tx, ty, tx + 6 * len(label) + 8, ty + 12), fill=(255, 220, 40))
        draw.text((tx + 2, ty), label, fill=(0, 0, 0), font=font)
        index += 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(dest)


def format_ocr_text(raw: str) -> str:
    """把 OCR 原文收成可读行：去掉 ``\\( \\)``，把 ``\\times`` 换成 ×。"""
    lines: list[str] = []
    for line in raw.splitlines():
        text = line.strip()
        if text.startswith("\\(") and text.endswith("\\)"):
            text = text[2:-2].strip()
        text = text.replace("\\times", "×").replace("\\div", "÷").replace("\\pm", "±")
        if text:
            lines.append(text)
    return "\n".join(lines)


def _short_path(path: Path, root: Path) -> str:
    """能相对仓库根则打印相对路径，否则用文件名。"""
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return path.name


def _section(index: int, title: str) -> None:
    """打印分步标题。"""
    print(flush=True)
    print(f"{index}. {title}", flush=True)


def _note(message: str) -> None:
    """打印缩进说明。"""
    print(f"   {message}", flush=True)


def _format_window(window: WindowBox) -> str:
    """窗口位置与尺寸的一行摘要。"""
    side = "已展开历史栏" if window.has_sidebar else "无历史栏"
    return f"位置 ({window.x}, {window.y})  大小 {window.w}×{window.h}  {side}"


def _format_keypad(layout: dict[str, Rect]) -> list[str]:
    """把按键中心收成五行网格。"""
    rows: list[str] = []
    for names in KEYPAD_ROWS:
        cells: list[str] = []
        for name in names:
            box = layout[name]
            cells.append(f"{name}({box.cx},{box.cy})")
        rows.append("    " + "  ".join(cells))
    return rows


def _parse_json(result: str | ToolResult) -> dict:
    """尝试把工具文本当成 JSON；失败返回空字典。"""
    try:
        payload = json.loads(_result_text(result))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ocr_start_fn(settings: Settings, log_path: Path):
    """把 OCR vLLM 的标准输出写到演示目录，便于排查预热失败。"""

    def start() -> subprocess.Popen[bytes]:
        """启动 OCR vLLM，日志追加到 ``log_path``。"""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("ab", buffering=0)
        env = os.environ.copy()
        env.setdefault("VLLM_HOST_IP", "127.0.0.1")
        env.setdefault("MASTER_ADDR", "127.0.0.1")
        env.setdefault("GLOO_SOCKET_IFNAME", "lo0")
        return subprocess.Popen(
            ocr_serve_command(settings),
            env=env,
            stdout=handle,
            stderr=handle,
        )

    return start


async def warm_ocr(ocr: OcrRuntime, log_path: Path) -> str:
    """在调用 ``ocr`` 工具前拉起服务并等到健康检查通过。

    参数：
        ocr: 将交给注册表复用的运行时。
        log_path: vLLM 日志。

    返回：
        中文状态，成功为「就绪」。
    """
    if not weights_ready(ocr.settings.ocr_model_path):
        return f"缺少 OCR 权重：{ocr.settings.ocr_model_path}"
    try:
        resolve_vllm_bin()
    except MissingVllmError as exc:
        return str(exc)
    try:
        await ocr.ensure_server()
    except (OcrUnavailable, MissingVllmError, OSError) as exc:
        hint = _ocr_log_hint(log_path)
        return f"预热失败：{exc}。{hint}日志 {_short_path(log_path, ocr.settings.project_root)}"
    return "就绪"


def _ocr_log_hint(log_path: Path) -> str:
    """从 vLLM 日志里抽出最后一条 ValueError / RuntimeError，便于对照。"""
    if not log_path.is_file():
        return ""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if "ValueError:" in stripped or "RuntimeError:" in stripped:
            return stripped.split("Error:", 1)[-1].strip() + " "
    return ""


async def _invoke(registry: ToolRegistry, name: str, args: dict | None = None) -> str | ToolResult:
    """调用工具，不向终端倾倒原始 JSON。"""
    return await registry.invoke(name, args or {})


async def _click_rect(registry: ToolRegistry, box: Rect) -> str:
    """按当前视图帧点击矩形中心，返回一行中文结果。"""
    vx, vy = _view_point(box.cx, box.cy)
    result = await _invoke(registry, "mouse_click", {"x": vx, "y": vy})
    await asyncio.sleep(CLICK_PAUSE)
    return _result_text(result)


async def _refresh_region(registry: ToolRegistry, window: WindowBox) -> Path | None:
    """按当前窗口再截一张区域图，刷新视图坐标系。"""
    shot = await _invoke(registry, "screenshot", {"region": window.region, "show_cursor": False})
    return _screenshot_path(shot)


async def _click_history_toggle(registry: ToolRegistry, window: WindowBox) -> WindowBox:
    """窄窗口时点击标题栏历史按钮，然后重读窗口。"""
    toggle_x = window.x + round(window.w * 0.58)
    toggle_y = window.y + 14
    vx, vy = _view_point(toggle_x, toggle_y)
    await _invoke(registry, "mouse_click", {"x": vx, "y": vy})
    await asyncio.sleep(0.45)
    return read_calculator_window()


async def run_demo() -> int:
    """执行完整演示。成功返回 0，环境不满足返回 1。"""
    if platform.system() != "Darwin":
        print("本演示只支持 macOS。", file=sys.stderr)
        return 1

    print("第二周演示：桌面感知与控制（macOS 计算器）", flush=True)
    print("请勿把指针甩到屏幕左上角，否则 PyAutoGUI 会紧急停止。", flush=True)
    for remain in range(COUNTDOWN_SECONDS, 0, -1):
        print(f"   {remain}…", flush=True)
        await asyncio.sleep(1)

    loaded = load_settings()
    root = loaded.project_root
    settings = replace(
        loaded,
        screenshots_dir=(root / "artifacts" / "week2-demo").resolve(),
        # 0.2 在 Metal 上第一轮编译开销大，KV 预算为负；演示单独提高到 0.45。
        ocr_gpu_memory_utilization=max(loaded.ocr_gpu_memory_utilization, 0.45),
    )
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
    current_session_id.set("week2-demo")
    ocr_log = settings.screenshots_dir / "ocr-vllm.log"
    ocr = OcrRuntime(settings, start_fn=_ocr_start_fn(settings, ocr_log))
    ocr_task = asyncio.create_task(warm_ocr(ocr, ocr_log))
    registry = build_default_registry(settings, gate=AutoApproveGate(), ocr=ocr)

    try:
        open_calculator()
        window = wait_for_calculator_window()
    except RuntimeError as exc:
        ocr_task.cancel()
        print(str(exc), file=sys.stderr)
        return 1

    _section(1, "屏幕")
    info = _parse_json(await _invoke(registry, "screen_info"))
    _note(
        f"分辨率 {info.get('screen_width')}×{info.get('screen_height')}"
        f"  scale={info.get('scale')}  指针 ({info.get('mouse_x')}, {info.get('mouse_y')})"
    )
    full = await _invoke(registry, "screenshot", {"show_cursor": True})
    full_path = _screenshot_path(full)
    if full_path:
        _note(f"全屏截图  {_short_path(full_path, root)}")

    window = ensure_history_sidebar()
    if not window.has_sidebar:
        _note("菜单未展开历史栏，改点标题栏按钮")
        await _refresh_region(registry, window)
        window = await _click_history_toggle(registry, window)
    if not window.has_sidebar:
        _note(f"历史栏仍未展开（宽 {window.w}），滚动将点窗口左三分之一")

    _section(2, "计算器窗口")
    _note(_format_window(window))
    ax = read_ax_layout()
    layout = calculator_layout(window, controls=ax or None)
    if ax:
        _note("按键框来自辅助功能，不再均分窗口")
    else:
        _note("未读到控件，使用几何网格")
    if "history" in layout:
        hist = layout["history"]
        _note(f"历史栏中心  ({hist.cx}, {hist.cy})")
    drag = layout["drag"]
    _note(f"拖拽空白  ({drag.cx}, {drag.cy})")
    _note("按键中心：")
    for row in _format_keypad(layout):
        print(row, flush=True)

    region_path = await _refresh_region(registry, window)
    if region_path is None:
        print("区域截图失败", file=sys.stderr)
        ocr_task.cancel()
        return 1
    boxed = settings.screenshots_dir / f"{region_path.stem}-boxes.png"
    draw_layout_boxes(region_path, layout, window, boxed)
    _note(f"窗口截图  {_short_path(region_path, root)}")
    _note(f"编号框    {_short_path(boxed, root)}")

    _section(3, "点按  AC  1  2  +  3  4  =")
    await _click_rect(registry, layout["display"])
    clicks = []
    failed = False
    for key in ("AC", "1", "2", "+", "3", "4", "="):
        text = await _click_rect(registry, layout[key])
        box = layout[key]
        clicks.append(f"{key}({box.cx},{box.cy})")
        if "已单击" not in text:
            failed = True
            _note(f"{key} 失败：{text}")
    _note(" → ".join(clicks))
    if not failed:
        _note("点按完成")

    _section(4, "键盘  清除后输入 5*6 回车")
    await _click_rect(registry, layout["display"])
    await _invoke(registry, "keyboard_press", {"keys": "c", "delay_ms": 80})
    await _invoke(registry, "keyboard_type", {"text": "5*6", "delay_ms": 80})
    await _invoke(registry, "keyboard_press", {"keys": "enter", "delay_ms": 80})
    await asyncio.sleep(0.3)
    _note("已发送  c  →  5*6  →  Enter")

    _section(5, "OCR")
    result_path = await _refresh_region(registry, window)
    ocr_status = await ocr_task
    _note(ocr_status)
    if result_path is not None:
        ocr_result = await _invoke(registry, "ocr", {"path": str(result_path)})
        text = _result_text(ocr_result)
        if "不可用" in text or "工具错误" in text:
            _note(f"识别未成功。日志 {_short_path(ocr_log, root)}")
        else:
            _note(f"截图  {_short_path(result_path, root)}")
            pretty = format_ocr_text(text)
            for line in pretty.splitlines():
                _note(line)

    _section(6, "滚动历史栏")
    scroll_box = layout.get("history") or layout.get("sidebar")
    if scroll_box is None:
        scroll_box = Rect(
            "fallback_scroll",
            window.x + 20,
            window.y + TITLE_H + 20,
            max(40, window.w // 3),
            max(40, window.h // 2),
        )
    sx, sy = _view_point(scroll_box.cx, scroll_box.cy)
    down = _result_text(await _invoke(registry, "mouse_scroll", {"clicks": -4, "x": sx, "y": sy}))
    await asyncio.sleep(0.2)
    up = _result_text(await _invoke(registry, "mouse_scroll", {"clicks": 3, "x": sx, "y": sy}))
    _note(f"位置 ({scroll_box.cx}, {scroll_box.cy})")
    _note(down.split("（")[0])
    _note(up.split("（")[0])

    _section(7, "拖拽窗口")
    origin = window
    v1 = _view_point(drag.cx, drag.cy)
    v2 = _view_point(drag.cx + DRAG_OFFSET[0], drag.cy + DRAG_OFFSET[1])
    _note(f"从空白标题区 ({drag.cx}, {drag.cy}) 偏移 {DRAG_OFFSET}")
    await _invoke(
        registry,
        "mouse_drag",
        {"x1": v1[0], "y1": v1[1], "x2": v2[0], "y2": v2[1], "duration": 0.45},
    )
    await asyncio.sleep(0.25)
    moved = read_calculator_window()
    _note(f"拖后  ({moved.x}, {moved.y})")
    await _refresh_region(registry, moved)
    back = calculator_layout(moved)["drag"]
    dx, dy = origin.x - moved.x, origin.y - moved.y
    b1 = _view_point(back.cx, back.cy)
    b2 = _view_point(back.cx + dx, back.cy + dy)
    await _invoke(
        registry,
        "mouse_drag",
        {"x1": b1[0], "y1": b1[1], "x2": b2[0], "y2": b2[1], "duration": 0.45},
    )
    restored = read_calculator_window()
    after = await _invoke(registry, "screenshot", {"region": restored.region, "show_cursor": True})
    _note(f"拖回  ({restored.x}, {restored.y})")

    _section(8, "产物")
    after_path = _screenshot_path(after)
    _note(_short_path(settings.screenshots_dir, root))
    if after_path:
        _note(f"末张  {_short_path(after_path, root)}")
    return 0


def main() -> None:
    """命令行入口。"""
    raise SystemExit(asyncio.run(run_demo()))


if __name__ == "__main__":
    main()
