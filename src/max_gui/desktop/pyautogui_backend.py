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
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    return pyautogui


class PyAutoGUIBackend:
    def size(self) -> tuple[int, int]:
        width, height = _pyautogui().size()
        return int(width), int(height)

    def position(self) -> tuple[int, int]:
        point = _pyautogui().position()
        return int(point.x), int(point.y)

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Image.Image:
        try:
            image = _pyautogui().screenshot(region=region)
        except Exception as exc:
            raise DesktopPermissionError("screen_recording", SCREEN_RECORDING_HELP) from exc
        return image.convert("RGB")

    def move_to(self, x: int, y: int, duration: float = 0.2) -> None:
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
        def _run(gui: Any) -> None:
            gui.moveTo(x1, y1, duration=min(duration, 0.2))
            gui.dragTo(x2, y2, duration=duration, button=button)

        self._input(_run)

    def write(self, text: str, interval: float = 0.0) -> None:
        self._input(lambda gui: gui.write(text, interval=interval))

    def press(self, key: str) -> None:
        self._input(lambda gui: gui.press(key))

    def hotkey(self, *keys: str) -> None:
        self._input(lambda gui: gui.hotkey(*keys))

    def paste(self, text: str) -> None:
        def _run(gui: Any) -> None:
            import pyperclip

            pyperclip.copy(text)
            gui.hotkey("command", "v")

        self._input(_run)

    def _input(self, fn: Any) -> None:
        try:
            fn(_pyautogui())
        except DesktopPermissionError:
            raise
        except Exception as exc:
            raise DesktopPermissionError("accessibility", ACCESSIBILITY_HELP) from exc
