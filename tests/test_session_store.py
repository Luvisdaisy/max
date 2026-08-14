from __future__ import annotations

from pathlib import Path

from max_gui.config import Settings
from max_gui.session.store import SessionMessage, SessionStore


def test_create_resume_and_switch(settings: Settings) -> None:
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


def test_missing_image_placeholder(settings: Settings, tmp_path: Path) -> None:
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
