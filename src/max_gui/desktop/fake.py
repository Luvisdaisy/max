"""测试用桌面后端：记录调用、维护指针，并可注入权限失败。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from max_gui.desktop.backend import DesktopPermissionError


@dataclass
class FakeDesktopBackend:
    """内存假屏幕。默认 1440×900 逻辑像素、scale=2 的纯色图。

    字段：
        calls: `(方法名, 参数字典)` 调用记录。
        fail_screenshot: 为真时返回全黑图，模拟无屏幕录制权限。
        fail_input: 为真时键鼠抛出辅助功能错误。
        fixture: 若给出则作为截图源图。
    """

    screen_size: tuple[int, int] = (1440, 900)
    mouse: tuple[int, int] = (10, 20)
    scale: float = 2.0
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    fail_screenshot: bool = False
    fail_input: bool = False
    fixture: Image.Image | None = None

    def size(self) -> tuple[int, int]:
        """返回配置的逻辑分辨率。"""
        return self.screen_size

    def position(self) -> tuple[int, int]:
        """返回当前记录的指针位置。"""
        return self.mouse

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Image.Image:
        """按 scale 生成或裁剪假截图。`fail_screenshot` 时返回全黑图。"""
        self.calls.append(("screenshot", {"region": region}))
        if self.fail_screenshot:
            width, height = self.screen_size
            return Image.new(
                "RGB", (int(width * self.scale), int(height * self.scale)), color="black"
            )
        if self.fixture is not None:
            image = self.fixture.copy()
        else:
            width, height = self.screen_size
            image = Image.new(
                "RGB", (int(width * self.scale), int(height * self.scale)), color=(40, 80, 160)
            )
        if region is not None:
            x, y, w, h = region
            box = (
                int(x * self.scale),
                int(y * self.scale),
                int((x + w) * self.scale),
                int((y + h) * self.scale),
            )
            return image.crop(box)
        return image

    def move_to(self, x: int, y: int, duration: float = 0.2) -> None:
        """记录移动并更新指针。"""
        self._ensure_input()
        self.calls.append(("move_to", {"x": x, "y": y, "duration": duration}))
        self.mouse = (x, y)

    def click(
        self,
        *,
        button: str = "left",
        clicks: int = 1,
        x: int | None = None,
        y: int | None = None,
        duration: float = 0.2,
    ) -> None:
        """记录点击；给出坐标时先更新指针。"""
        self._ensure_input()
        if x is not None and y is not None:
            self.mouse = (x, y)
        self.calls.append(
            ("click", {"button": button, "clicks": clicks, "x": x, "y": y, "duration": duration})
        )

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
        """记录拖拽，指针停在终点。"""
        self._ensure_input()
        self.mouse = (x2, y2)
        self.calls.append(
            (
                "drag_to",
                {"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration": duration, "button": button},
            )
        )

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> None:
        """记录滚动；给出坐标时先更新指针。"""
        self._ensure_input()
        if x is not None and y is not None:
            self.mouse = (x, y)
        self.calls.append(("scroll", {"clicks": clicks, "x": x, "y": y}))

    def write(self, text: str, interval: float = 0.0) -> None:
        """记录逐键输入。"""
        self._ensure_input()
        self.calls.append(("write", {"text": text, "interval": interval}))

    def press(self, key: str) -> None:
        """记录单键。"""
        self._ensure_input()
        self.calls.append(("press", {"key": key}))

    def hotkey(self, *keys: str) -> None:
        """记录组合键。"""
        self._ensure_input()
        self.calls.append(("hotkey", {"keys": list(keys)}))

    def paste(self, text: str) -> None:
        """记录剪贴板粘贴。"""
        self._ensure_input()
        self.calls.append(("paste", {"text": text}))

    def _ensure_input(self) -> None:
        """`fail_input` 时抛出辅助功能权限错误。"""
        if self.fail_input:
            raise DesktopPermissionError(
                "accessibility",
                "辅助功能权限不足",
            )
