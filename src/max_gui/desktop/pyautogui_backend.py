"""基于 PyAutoGUI 的真实桌面后端；权限失败转成带指引的 `DesktopPermissionError`。"""

from __future__ import annotations

from typing import Any

from PIL import Image

from max_gui.desktop.backend import DesktopPermissionError

SCREEN_RECORDING_HELP = (
    "截图失败：看起来没有屏幕录制权限（图像全黑或过小）。"
    "请打开 系统设置 → 隐私与安全性 → 屏幕录制，勾选运行 max-gui 的终端"
    "（Terminal / iTerm / VS Code），然后重启该终端。"
)
ACCESSIBILITY_HELP = (
    "键鼠操作失败：看起来没有辅助功能权限。"
    "请打开 系统设置 → 隐私与安全性 → 辅助功能，勾选运行 max-gui 的终端，然后重启该终端。"
)


def _pyautogui() -> Any:
    """延迟导入并打开 failsafe / 短暂停顿。"""
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    return pyautogui


class PyAutoGUIBackend:
    """调用本机 PyAutoGUI。截图失败视为缺屏幕录制，键鼠失败视为缺辅助功能。"""

    def size(self) -> tuple[int, int]:
        """主屏逻辑宽高。"""
        width, height = _pyautogui().size()
        return int(width), int(height)

    def position(self) -> tuple[int, int]:
        """当前指针逻辑坐标。"""
        point = _pyautogui().position()
        return int(point.x), int(point.y)

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Image.Image:
        """截主屏或区域并转为 RGB。"""
        try:
            image = _pyautogui().screenshot(region=region)
        except Exception as exc:
            raise DesktopPermissionError("screen_recording", SCREEN_RECORDING_HELP) from exc
        return image.convert("RGB")

    def move_to(self, x: int, y: int, duration: float = 0.2) -> None:
        """平滑移动指针。"""
        self._input(lambda gui: gui.moveTo(x, y, duration=duration))

    def click(
        self,
        *,
        button: str = "left",
        clicks: int = 1,
        x: int | None = None,
        y: int | None = None,
        duration: float = 0.2,
    ) -> None:
        """可选先移动再点击。"""

        def _run(gui: Any) -> None:
            if x is not None and y is not None:
                gui.moveTo(x, y, duration=duration)
            gui.click(button=button, clicks=clicks)

        self._input(_run)

    def drag_to(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        *,
        duration: float = 0.2,
        button: str = "left",
    ) -> None:
        """先移到起点再拖到终点。"""

        def _run(gui: Any) -> None:
            gui.moveTo(x1, y1, duration=min(duration, 0.2))
            gui.dragTo(x2, y2, duration=duration, button=button)

        self._input(_run)

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> None:
        """可选先移动再滚动。正数向上。"""

        def _run(gui: Any) -> None:
            if x is not None and y is not None:
                gui.moveTo(x, y)
            gui.scroll(clicks)

        self._input(_run)

    def write(self, text: str, interval: float = 0.0) -> None:
        """逐键输入 ASCII。"""
        self._input(lambda gui: gui.write(text, interval=interval))

    def press(self, key: str) -> None:
        """按下单个键。"""
        self._input(lambda gui: gui.press(key))

    def hotkey(self, *keys: str) -> None:
        """按下组合键。"""
        self._input(lambda gui: gui.hotkey(*keys))

    def paste(self, text: str) -> None:
        """复制到剪贴板后发送 Command+V。会覆盖系统剪贴板。"""

        def _run(gui: Any) -> None:
            import pyperclip

            pyperclip.copy(text)
            gui.hotkey("command", "v")

        self._input(_run)

    def _input(self, fn: Any) -> None:
        """执行键鼠回调；未知异常包装为辅助功能权限错误。"""
        try:
            fn(_pyautogui())
        except DesktopPermissionError:
            raise
        except Exception as exc:
            raise DesktopPermissionError("accessibility", ACCESSIBILITY_HELP) from exc
