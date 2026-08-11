"""桌面会话互斥与输入状态清理的可注入实现。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from threading import Lock, RLock


class DesktopSessionBusy(RuntimeError):
    """另一个任务正在持有物理桌面控制权。"""


class DesktopSessionLock:
    """进程内桌面控制锁；重复释放不会影响其他任务。"""

    def __init__(self) -> None:
        self._mutex = Lock()
        self._state_lock = RLock()
        self._owner: str | None = None

    @property
    def owner(self) -> str | None:
        with self._state_lock:
            return self._owner

    def acquire(self, task_id: str) -> None:
        with self._state_lock:
            if self._owner == task_id:
                return
        if not self._mutex.acquire(blocking=False):
            raise DesktopSessionBusy("desktop session is busy")
        with self._state_lock:
            self._owner = task_id

    def release(self, task_id: str) -> None:
        with self._state_lock:
            if self._owner != task_id:
                return
            self._owner = None
            self._mutex.release()


class InputStateCleaner:
    """逐项执行释放动作，单项失败不阻断剩余清理。"""

    def __init__(self, releases: Iterable[Callable[[], None]] = ()) -> None:
        self._releases = tuple(releases)

    def cleanup(self) -> list[str]:
        errors: list[str] = []
        for release in self._releases:
            try:
                release()
            except Exception as error:
                errors.append(f"{type(error).__name__}: {error}")
        return errors
