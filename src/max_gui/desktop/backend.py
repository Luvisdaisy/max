from __future__ import annotations

from typing import Protocol

from PIL import Image


class DesktopPermissionError(RuntimeError):
    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        super().__init__(message)


class DesktopBackend(Protocol):
    def size(self) -> tuple[int, int]: ...

    def position(self) -> tuple[int, int]: ...

    def screenshot(self, region: tuple[int, int, int, int] | None = None) -> Image.Image: ...

    def move_to(self, x: int, y: int, duration: float = 0.2) -> None: ...

    def click(
        self,
        *,
        button: str = "left",
        clicks: int = 1,
        x: int | None = None,
        y: int | None = None,
        duration: float = 0.2,
    ) -> None: ...

    def drag_to(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        *,
        duration: float = 0.2,
        button: str = "left",
    ) -> None: ...

    def write(self, text: str, interval: float = 0.0) -> None: ...

    def press(self, key: str) -> None: ...

    def hotkey(self, *keys: str) -> None: ...

    def paste(self, text: str) -> None: ...
