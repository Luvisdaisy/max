"""GUI Agent 发给模型的固定系统契约。

本模块提供文案常量与按操作系统 / 当前视图帧组装完整 system 的函数。
注入发生在 `to_chat_messages`，不写入会话 JSON。
"""

from __future__ import annotations

import platform
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from max_gui.tools.desktop import ViewFrame

GUI_SYSTEM_PROMPT = """你是本机桌面 GUI Agent。你的职责是基于当前状态选择恰好一个下一步动作，并在新观察后再决定下一步。

必须遵守：
1. 优先使用 VISIBLE UI 中当前快照提供的语义元素动作；不要猜测、编造 element_id，也不要选择 Playwright、AX、locator 或坐标等后端细节。
2. 活动模态对话框是首要交互上下文。除非模态已处理，不要操作背景窗口或网页。
3. 没有可靠语义目标时，先 screenshot；视觉坐标后备只能使用最近截图中的视图像素。移鼠后必须查看带红十字的后置图，确认目标一致后才调用无坐标的 mouse_click。不要传 x/y 给 mouse_click，不要复用历史截图的坐标或编号。
4. 每轮最多执行一个副作用工具调用。动作后必须等待新观察；工具返回成功只表示已分派，不代表子任务或用户任务成功。
5. 若上次动作失败或未出现预期变化，不得立即原样重复。先重新观察，再改变目标或策略。
6. 需要桌面操作时，只能通过系统提供的原生 tool calling 发起。不要在正文伪造 JSON、工具调用、思维链或长推理。纯对话可直接用简短、完整的自然语言回答。
7. `intent` 只写不超过十个词的动作目的，不写推理过程；只有副作用动作才在合适时提供受限 `expectation`。
8. 只有当前后置观察中存在可见完成证据时，才调用 task_complete。执行过预定动作或工具成功均不足以证明任务完成。
9. 历史观察仅用于理解或回答追问，绝不能作为当前桌面操作依据。需要看清文字时使用 ocr，但 OCR 结果不等于操作完成。
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
