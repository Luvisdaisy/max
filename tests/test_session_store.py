"""会话存储：创建/恢复/切换、桌面自动批准默认值、缺失图像标记。"""

from __future__ import annotations

from pathlib import Path

from max_gui.config import Settings
from max_gui.session.store import SessionMessage, SessionStore


def test_create_resume_and_switch(settings: Settings) -> None:
    """默认打开最近会话；`force_new` 另建；`get` 可切回旧会话。"""
    store = SessionStore(settings.sessions_dir)
    first = store.open_or_create(model="qwen3.5-2b")
    assert first.id
    assert (settings.sessions_dir / f"{first.id}.json").is_file()
    store.append_messages(
        first,
        [SessionMessage(role="user", content={"text": "你好", "images": []})],
    )

    resumed = store.open_or_create(model="qwen3.5-2b")
    assert resumed.id == first.id
    assert resumed.messages[0].content["text"] == "你好"

    created = store.open_or_create(model="qwen3.5-2b", force_new=True)
    assert created.id != first.id
    listed = store.list()
    ids = {item.id for item in listed}
    assert first.id in ids and created.id in ids

    switched = store.get(first.id)
    assert switched is not None
    assert switched.messages[0].content["text"] == "你好"


def test_auto_approve_desktop_default_and_legacy(settings: Settings, tmp_path: Path) -> None:
    """新建与缺字段的旧 JSON 都将 `auto_approve_desktop` 视为关。"""
    store = SessionStore(settings.sessions_dir)
    created = store.create(model="qwen3.5-2b")
    assert created.auto_approve_desktop is False
    loaded = store.get(created.id)
    assert loaded is not None
    assert loaded.auto_approve_desktop is False

    legacy = settings.sessions_dir / "legacy.json"
    legacy.write_text(
        '{"id": "legacy", "title": "旧", "model": "qwen3.5-2b", '
        '"created_at": "2026-08-14T00:00:00", "updated_at": "2026-08-14T00:00:00", '
        '"messages": []}',
        encoding="utf-8",
    )
    old = store.get("legacy")
    assert old is not None
    assert old.auto_approve_desktop is False
    assert old.view_frame is None
    assert old.locate_hits == {}


def test_view_frame_and_locate_hits_roundtrip(settings: Settings) -> None:
    """视图坐标系与定位表写入后再读回。"""
    store = SessionStore(settings.sessions_dir)
    session = store.create(model="qwen3.5-2b")
    session.view_frame = {
        "origin_x": 0,
        "origin_y": 0,
        "logical_width": 1920,
        "logical_height": 1080,
        "view_width": 1536,
        "view_height": 864,
        "image_path": "/tmp/shot.png",
    }
    session.locate_hits = {"1": [220, 80]}
    store.save(session)
    loaded = store.get(session.id)
    assert loaded is not None
    assert loaded.view_frame is not None
    assert loaded.view_frame["view_width"] == 1536
    assert loaded.locate_hits == {"1": [220, 80]}


def test_assistant_reasoning_roundtrip(settings: Settings) -> None:
    """助手 `reasoning` 落盘后能读回；缺字段的旧消息仍可加载。"""
    store = SessionStore(settings.sessions_dir)
    session = store.create(model="qwen3.5-2b")
    store.append_messages(
        session,
        [
            SessionMessage(
                role="assistant",
                content={"text": "已完成", "reasoning": "先截图"},
            )
        ],
    )
    loaded = store.get(session.id)
    assert loaded is not None
    assert loaded.messages[0].content["reasoning"] == "先截图"
    assert loaded.messages[0].content["text"] == "已完成"

    legacy = settings.sessions_dir / "no-reason.json"
    legacy.write_text(
        '{"id": "no-reason", "title": "旧", "model": "qwen3.5-2b", '
        '"created_at": "2026-08-14T00:00:00", "updated_at": "2026-08-14T00:00:00", '
        '"messages": [{"role": "assistant", "content": {"text": "你好"}, '
        '"created_at": "2026-08-14T00:00:01"}]}',
        encoding="utf-8",
    )
    old = store.get("no-reason")
    assert old is not None
    assert "reasoning" not in old.messages[0].content
    assert old.messages[0].content["text"] == "你好"


def test_missing_image_placeholder(settings: Settings, tmp_path: Path) -> None:
    """附件路径不存在时加载后标 `missing`。"""
    store = SessionStore(settings.sessions_dir)
    session = store.create(model="qwen3.5-2b")
    missing = tmp_path / "gone.png"
    store.append_messages(
        session,
        [
            SessionMessage(
                role="user",
                content={"text": "看图", "images": [{"path": str(missing)}]},
            )
        ],
    )
    loaded = store.get(session.id)
    assert loaded is not None
    assert loaded.messages[0].content["images"][0]["missing"] is True
