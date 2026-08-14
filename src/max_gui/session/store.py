from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _timestamp_id(when: datetime | None = None) -> str:
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return stamp


@dataclass(slots=True)
class SessionMessage:
    role: str
    content: dict[str, Any]
    created_at: str = field(default_factory=_now)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMessage:
        return cls(
            role=str(data.get("role") or "user"),
            content=dict(data.get("content") or {}),
            created_at=str(data.get("created_at") or _now()),
        )


@dataclass(slots=True)
class Session:
    id: str
    title: str
    model: str
    created_at: str
    updated_at: str
    messages: list[SessionMessage] = field(default_factory=list)
    status: str = "done"
    auto_approve: bool = False
    auto_approve_desktop: bool = False
    checkpoint: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        messages = [SessionMessage.from_dict(item) for item in data.get("messages") or []]
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or "新会话"),
            model=str(data.get("model") or "qwen3.5-2b"),
            created_at=str(data.get("created_at") or _now()),
            updated_at=str(data.get("updated_at") or _now()),
            messages=messages,
            status=str(data.get("status") or "done"),
            auto_approve=bool(data.get("auto_approve") or False),
            auto_approve_desktop=bool(data.get("auto_approve_desktop") or False),
            checkpoint=data.get("checkpoint"),
        )


class SessionStore:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        return self.directory / f"{session_id}.json"

    def create(self, *, model: str, title: str = "新会话") -> Session:
        session_id = self._unique_id()
        now = _now()
        session = Session(
            id=session_id,
            title=title,
            model=model,
            created_at=now,
            updated_at=now,
        )
        self.save(session)
        return session

    def save(self, session: Session) -> None:
        session.updated_at = _now()
        path = self.path_for(session.id)
        tmp = path.with_suffix(".json.tmp")
        payload = json.dumps(session.to_dict(), ensure_ascii=False, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)

    def get(self, session_id: str) -> Session | None:
        path = self.path_for(session_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        session = Session.from_dict(data)
        self._mark_missing_images(session)
        return session

    def list(self) -> list[Session]:
        sessions: list[Session] = []
        for path in self.directory.glob("*.json"):
            if path.name.endswith(".tmp"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                sessions.append(Session.from_dict(data))
            except (OSError, json.JSONDecodeError, KeyError):
                continue
        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return sessions

    def latest(self) -> Session | None:
        items = self.list()
        return items[0] if items else None

    def open_or_create(self, *, model: str, force_new: bool = False) -> Session:
        if not force_new:
            existing = self.latest()
            if existing is not None:
                self._mark_missing_images(existing)
                return existing
        return self.create(model=model)

    def update(
        self, session: Session, *, title: str | None = None, model: str | None = None
    ) -> Session:
        if title is not None:
            session.title = title
        if model is not None:
            session.model = model
        self.save(session)
        return session

    def append_messages(self, session: Session, messages: list[SessionMessage]) -> Session:
        session.messages.extend(messages)
        if session.title == "新会话":
            for message in messages:
                if message.role == "user":
                    text = str(message.content.get("text") or "").strip()
                    if text:
                        session.title = text[:40]
                        break
        self.save(session)
        return session

    def load_messages(self, session_id: str) -> list[SessionMessage]:
        session = self.get(session_id)
        if session is None:
            return []
        return session.messages

    def _unique_id(self) -> str:
        base = _timestamp_id()
        candidate = base
        suffix = 2
        while self.path_for(candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _mark_missing_images(self, session: Session) -> None:
        for message in session.messages:
            images = message.content.get("images")
            if not isinstance(images, list):
                continue
            for item in images:
                if not isinstance(item, dict):
                    continue
                raw = item.get("path")
                if not raw:
                    continue
                item["missing"] = not Path(str(raw)).is_file()
