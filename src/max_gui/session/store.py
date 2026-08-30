"""会话 JSON 存储：按时间戳文件读写，并标记缺失的图像附件。"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from max_gui.agent.context import sanitize_grounded_facts


def _optional_dict(value: Any) -> dict[str, Any] | None:
    """非字典视为缺失。"""
    return dict(value) if isinstance(value, dict) else None


def _string_int_points(value: Any) -> dict[str, list[int]]:
    """把定位表收成 `{编号: [x, y]}`；坏项丢弃。"""
    if not isinstance(value, dict):
        return {}
    hits: dict[str, list[int]] = {}
    for key, point in value.items():
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            hits[str(int(key))] = [int(point[0]), int(point[1])]
        except (TypeError, ValueError):
            continue
    return hits


def _task_context(value: Any) -> dict[str, Any] | None:
    """恢复任务胶囊并过滤短期事实坏项，旧会话仍保留其余兼容字段。"""
    context = _optional_dict(value)
    if context is None:
        return None
    if "grounded_facts" in context:
        context["grounded_facts"] = sanitize_grounded_facts(context["grounded_facts"])
    return context


def _conversation_context(value: Any) -> dict[str, Any] | None:
    """恢复只读会话视觉上下文，拒绝可执行坐标与长正文。"""
    context = _optional_dict(value)
    if context is None:
        return None
    observation = context.get("observation")
    if not isinstance(observation, dict) or not observation.get("path"):
        return None
    return {
        "observation": {
            "path": str(observation["path"]),
            "source": str(observation.get("source") or "tool"),
            "captured_at": str(observation.get("captured_at") or ""),
        },
        "dialogue": [
            str(item)[:240] for item in context.get("dialogue") or [] if isinstance(item, str)
        ][-2:],
    }


def _run_summary(value: Any) -> dict[str, Any] | None:
    """恢复紧凑运行摘要，只保留可 JSON 化的标量诊断。"""
    if not isinstance(value, dict):
        return None
    allowed = {
        "run_id",
        "final_status",
        "terminal_reason",
        "iterations",
        "model_calls",
        "tool_calls",
        "tool_successes",
        "tool_failures",
        "duration_ms",
        "model_duration_ms",
        "tool_duration_ms",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "finish_reason",
    }
    result: dict[str, Any] = {}
    for key in allowed:
        item = value.get(key)
        if item is None or isinstance(item, (str, int, float, bool)):
            result[key] = item
    return result


def _now() -> str:
    """当前本地时区 ISO 时间，精确到秒。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _timestamp_id(when: datetime | None = None) -> str:
    """生成 `YYYYMMDD-HHMMSS` 形式的会话编号。"""
    stamp = (when or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return stamp


@dataclass(slots=True)
class SessionMessage:
    """会话中的一条消息。

    字段：
        role: `user` / `assistant` / `tool`。
        content: 通常含 `text`、`images`，助手还可能带 `tool_calls`
            与可选 `reasoning`；工具消息还可能含 `name` 与嵌套 `exec`。
        created_at: ISO 时间。
    """

    role: str
    content: dict[str, Any]
    created_at: str = field(default_factory=_now)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMessage:
        """从 JSON 对象恢复；缺字段用默认值。"""
        return cls(
            role=str(data.get("role") or "user"),
            content=dict(data.get("content") or {}),
            created_at=str(data.get("created_at") or _now()),
        )


@dataclass(slots=True)
class Session:
    """一次对话及其检查点。

    `auto_approve` 管工作区写/执行；`auto_approve_desktop` 管桌面点击与输入，
    二者独立。旧 JSON 缺字段时桌面自动批准默认为关。
    `view_frame` / `locate_hits` 保存最近一次截图坐标系与文字定位编号。
    """

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
    view_frame: dict[str, Any] | None = None
    locate_hits: dict[str, list[int]] = field(default_factory=dict)
    task_context: dict[str, Any] | None = None
    conversation_context: dict[str, Any] | None = None
    run_summary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        payload = asdict(self)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """从磁盘 JSON 恢复。缺少桌面批准或坐标系字段时用安全默认值。"""
        messages = [SessionMessage.from_dict(item) for item in data.get("messages") or []]
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or "新会话"),
            model=str(data.get("model") or "qwen3.5-4b"),
            created_at=str(data.get("created_at") or _now()),
            updated_at=str(data.get("updated_at") or _now()),
            messages=messages,
            status=str(data.get("status") or "done"),
            auto_approve=bool(data.get("auto_approve") or False),
            auto_approve_desktop=bool(data.get("auto_approve_desktop") or False),
            checkpoint=data.get("checkpoint"),
            view_frame=_optional_dict(data.get("view_frame")),
            locate_hits=_string_int_points(data.get("locate_hits")),
            task_context=_task_context(data.get("task_context")),
            conversation_context=_conversation_context(data.get("conversation_context")),
            run_summary=_run_summary(data.get("run_summary")),
        )


class SessionStore:
    """目录下每个会话一个 `<id>.json`，写入时先写临时文件再替换。"""

    def __init__(self, directory: Path) -> None:
        """参数：`directory` 为会话目录，不存在则创建。"""
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        """会话 JSON 的绝对路径。"""
        return self.directory / f"{session_id}.json"

    def create(self, *, model: str, title: str = "新会话") -> Session:
        """创建并立即落盘一个空会话。"""
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
        """刷新 `updated_at` 并原子写入。"""
        session.updated_at = _now()
        path = self.path_for(session.id)
        tmp = path.with_suffix(".json.tmp")
        payload = json.dumps(session.to_dict(), ensure_ascii=False, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)

    def get(self, session_id: str) -> Session | None:
        """按编号读取；不存在返回 `None`。会给缺失图像打 `missing`。"""
        path = self.path_for(session_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        session = Session.from_dict(data)
        self._mark_missing_images(session)
        return session

    def list(self) -> list[Session]:
        """列出可读会话，按 `updated_at` 降序。损坏文件跳过。"""
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
        """最近更新的会话，没有则 `None`。"""
        items = self.list()
        return items[0] if items else None

    def open_or_create(self, *, model: str, force_new: bool = False) -> Session:
        """打开最近会话；`force_new` 或目录为空时新建。"""
        if not force_new:
            existing = self.latest()
            if existing is not None:
                self._mark_missing_images(existing)
                return existing
        return self.create(model=model)

    def update(
        self, session: Session, *, title: str | None = None, model: str | None = None
    ) -> Session:
        """就地改标题或模型并保存。"""
        if title is not None:
            session.title = title
        if model is not None:
            session.model = model
        self.save(session)
        return session

    def append_messages(self, session: Session, messages: list[SessionMessage]) -> Session:
        """追加消息。标题仍为「新会话」时用首条用户文本前 40 字作标题。"""
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
        """读取会话消息；会话不存在返回空列表。"""
        session = self.get(session_id)
        if session is None:
            return []
        return session.messages

    def _unique_id(self) -> str:
        """同一秒冲突时追加 `-2`、`-3`…。"""
        base = _timestamp_id()
        candidate = base
        suffix = 2
        while self.path_for(candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _mark_missing_images(self, session: Session) -> None:
        """给 `content.images` 里路径已不存在的项标 `missing=True`。"""
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
