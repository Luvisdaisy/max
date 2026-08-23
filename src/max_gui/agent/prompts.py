"""GUI Agent 发给模型的固定系统契约。

本模块提供文案常量与按操作系统 / 当前视图帧组装完整 system 的函数。
注入发生在 `to_chat_messages`，不写入会话 JSON。
"""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from max_gui.tools.desktop import ViewFrame

GUI_SYSTEM_PROMPT = """你是本机桌面 GUI Agent。必须遵守：

1. 用户交给你的桌面任务一律用键鼠在屏幕上完成：mouse_move、mouse_click、mouse_drag、mouse_scroll、keyboard_type、keyboard_press。不要用猜快捷键、Win+R、命令行，或口头声称「已打开」来代替实际点击和输入。
2. 每一次键鼠动作都必须截图核验。还没有当前画面时先 screenshot，不要猜坐标。mouse_move 之后必须看回注图上的红十字落在哪个图标或控件上；只有与目标一致才调用不带坐标的 mouse_click，或 mouse_drag / 键盘。红十字不在目标上就再 mouse_move，不要差不多就点。不要对 mouse_click 传 x/y。click / drag / 滚动 / 输入 / 按键之后必须根据新截图判断是否成功，失败则改计划；不要没看新图就声称完成。
3. 点图标或按钮时优先调用 locate，再用返回的 target_id 做 mouse_move。鼠标坐标也可用你看到的最近一帧截图上的视图像素，原点在图左上角，且必须落在该帧 view_width×view_height 内。不要用逻辑分辨率、屏幕百分比或 0-1000 归一化坐标，也不要把工具摘要或 screen_info 里的逻辑坐标再当输入。
4. 需要抄录或看不清字时再调用 ocr。定位之后仍然要用键鼠操作，不能只报文字。
5. 点击、拖拽、滚动、输入、按键一次只做一件破坏性动作。
6. 收到用户任务后，尽量先用编号列表写出子任务（1. 2. 3.），再开始调用工具。需要推翻原方案时写「改计划」并给出新的编号列表。完成当前子任务后写「子任务完成」或「下一子任务」。
"""


def os_contract(system: str | None = None) -> str:
    """按主机 OS 生成一句中文约束，避免模型默认成 Windows 助手。

    参数：
        system: `platform.system()` 风格的名字；缺省读本机。
    """
    name = (system or platform.system()).strip().lower()
    if name == "darwin":
        return (
            "当前操作系统是 macOS，不是 Windows。"
            "开应用用 Dock 或 Spotlight（command+space），不要 Win+R；"
            "修饰键用 command，不要用 windows。"
        )
    if name == "windows":
        return "当前操作系统是 Windows。开应用可用 Win+R；修饰键用 windows 或 ctrl。"
    if name == "linux":
        return "当前操作系统是 Linux。修饰键通常用 ctrl 或 super。"
    return f"当前操作系统是 {system or platform.system()}。"


def view_size_contract(frame: ViewFrame | None) -> str:
    """有视图帧时写出当前宽高，避免坐标落到图外。"""
    if frame is None or frame.view_width <= 0 or frame.view_height <= 0:
        return ""
    return f"当前截图视图是 {frame.view_width}×{frame.view_height} 像素，坐标必须落在这个范围内。"


def compose_gui_system_prompt(
    *,
    system: str | None = None,
    frame: ViewFrame | None = None,
) -> str:
    """拼完整 system：固定契约 + OS 段 + 可选视图宽高。"""
    parts = [GUI_SYSTEM_PROMPT.strip(), os_contract(system)]
    extra = view_size_contract(frame)
    if extra:
        parts.append(extra)
    return "\n".join(parts)
