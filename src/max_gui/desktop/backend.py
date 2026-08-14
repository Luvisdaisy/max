"""桌面后端协议：逻辑像素坐标下的截图与键鼠，以及权限错误。"""

from __future__ import annotations

from typing import Protocol

from PIL import Image


class DesktopPermissionError(RuntimeError):
    """系统未授予屏幕录制或辅助功能权限。

    字段：
        kind: `screen_recording` 或 `accessibility`。
    """

    def __init__(self, kind: str, message: str) -> None:
        """参数：`kind` 权限类别；`message` 给用户的操作指引。"""
        self.kind = kind
        super().__init__(message)


class DesktopBackend(Protocol):
    """截图与键鼠的后端契约。坐标一律为逻辑像素。"""

    def size(self) -> tuple[int, int]:
        """主屏逻辑宽高。"""
        ...

    def position(self) -> tuple[int, int]:
        """当前指针逻辑坐标。"""
        ...

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Image.Image:
        """截取主屏或 `(x, y, width, height)` 区域，返回 RGB 图（可能按 scale 放大）。"""
        ...

    def move_to(self, x: int, y: int, duration: float = 0.2) -> None:
        """把指针移到逻辑坐标。参数：`duration` 为移动秒数。"""
        ...

    def click(
        self,
        *,
        button: str = "left",
        clicks: int = 1,
        x: int | None = None,
        y: int | None = None,
        duration: float = 0.2,
    ) -> None:
        """单击或双击。`x`/`y` 同时给出时先移动。"""
        ...

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
        """从 `(x1, y1)` 拖到 `(x2, y2)`。"""
        ...

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> None:
        """滚动滚轮。`clicks` 正数向上；给出 `x`/`y` 时先移动。"""
        ...

    def write(self, text: str, interval: float = 0.0) -> None:
        """逐键输入 ASCII 文本。`interval` 为键间隔秒。"""
        ...

    def press(self, key: str) -> None:
        """按下单个命名键。"""
        ...

    def hotkey(self, *keys: str) -> None:
        """同时按下组合键。"""
        ...

    def paste(self, text: str) -> None:
        """经剪贴板粘贴，用于非 ASCII。会覆盖系统剪贴板。"""
        ...
