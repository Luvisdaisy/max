"""任务隔离的内存资源存储，避免截图通过路径或 JSON 传播。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from threading import RLock
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResourceRef(BaseModel):
    """不可猜测、带任务作用域和类型的资源引用。"""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=16)
    task_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)


@dataclass(slots=True)
class _Entry:
    task_id: str
    kind: str
    value: Any


class ResourceError(ValueError):
    """引用未知、跨任务、类型错误或已经释放。"""


class InMemoryResourceStore:
    """仅在内存中保存任务资源，并提供幂等任务级释放。"""

    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}
        self._lock = RLock()

    def put(self, task_id: str, kind: str, value: Any) -> ResourceRef:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._entries[token] = _Entry(task_id, kind, value)
        return ResourceRef(id=token, task_id=task_id, kind=kind)

    def get(self, ref: ResourceRef, task_id: str, kind: str | None = None) -> Any:
        with self._lock:
            entry = self._entries.get(ref.id)
            if entry is None:
                raise ResourceError("resource is unknown or already released")
            if ref.task_id != task_id or entry.task_id != task_id:
                raise ResourceError("resource belongs to another task")
            if ref.kind != entry.kind or (kind is not None and entry.kind != kind):
                raise ResourceError("resource type does not match")
            return entry.value

    def release(self, ref: ResourceRef, task_id: str) -> None:
        with self._lock:
            entry = self._entries.get(ref.id)
            if entry is None:
                return
            if ref.task_id != task_id or entry.task_id != task_id:
                raise ResourceError("resource belongs to another task")
            del self._entries[ref.id]

    def clear_task(self, task_id: str) -> None:
        with self._lock:
            for token in [
                key for key, value in self._entries.items() if value.task_id == task_id
            ]:
                del self._entries[token]

    def count(self, task_id: str | None = None) -> int:
        with self._lock:
            if task_id is None:
                return len(self._entries)
            return sum(entry.task_id == task_id for entry in self._entries.values())
