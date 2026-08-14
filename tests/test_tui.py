"""TUI：斜杠命令、附件、会话恢复、Enter 发送与流式单条消息。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from textual.widgets import RichLog, Static

from max_gui.app import MaxGuiApp
from max_gui.config import Settings
from max_gui.session.store import SessionMessage, SessionStore
from max_gui.widgets.prompt import PromptInput


async def test_unknown_command_does_not_call_model(settings: Settings) -> None:
    """未知斜杠命令不启动回合。"""
    app = MaxGuiApp(settings, force_new=True)
    async with app.run_test() as pilot:
        await app._handle_command("/not-a-command")
        assert app._turn_active is False
        await pilot.pause()


async def test_attach_and_empty_send(settings: Settings, tmp_path: Path) -> None:
    """空发送忽略；附件校验、`/new` 清空队列；列表与中断命令可执行。"""
    image = tmp_path / "photo.png"
    Image.new("RGB", (8, 8), color="green").save(image)
    app = MaxGuiApp(settings, force_new=True)
    async with app.run_test() as pilot:
        await app._handle_submit("   ")
        assert app._turn_active is False
        await app._handle_command("/attach ./missing.png")
        assert app.pending_images == []
        await app._handle_command(f"/attach {image}")
        assert app.pending_images == [image.resolve()]
        await app._handle_command("/new")
        assert app.pending_images == []
        assert app.session is not None
        await app._handle_command("/sessions")
        await app._handle_command("/interrupt")
        await pilot.pause()


async def test_resume_after_restart(settings: Settings) -> None:
    """重启应用默认打开上次会话并看到历史。"""
    store = SessionStore(settings.sessions_dir)
    session = store.create(model="qwen3.5-2b")
    store.append_messages(
        session, [SessionMessage(role="user", content={"text": "上次的话", "images": []})]
    )
    app = MaxGuiApp(settings, force_new=False)
    async with app.run_test() as pilot:
        assert app.session is not None
        assert app.session.id == session.id
        assert any(msg.content.get("text") == "上次的话" for msg in app.session.messages)
        await pilot.pause()


async def test_enter_sends_nonempty_and_ignores_empty(settings: Settings) -> None:
    """Enter 提交当前文本并清空输入框。"""
    submitted: list[str] = []

    async def capture(raw: str) -> None:
        submitted.append(raw)

    app = MaxGuiApp(settings, force_new=True)
    app._handle_submit = capture  # type: ignore[method-assign]
    async with app.run_test() as pilot:
        prompt = app.query_one(PromptInput)
        await pilot.press("enter")
        assert submitted == [""]
        prompt.text = "hello from enter"
        await pilot.press("enter")
        await pilot.pause()
        assert submitted == ["", "hello from enter"]
        assert prompt.text == ""


async def test_stream_tokens_stay_on_one_message(settings: Settings) -> None:
    """流式 token 先聚在 `#live`，flush 后只写入一条历史。"""
    app = MaxGuiApp(settings, force_new=True)
    async with app.run_test() as pilot:
        app._append_token("已成功", started=False)
        app._append_token("执行", started=True)
        app._append_token(":", started=True)
        app._append_token("1", started=True)
        app._append_token(". **Screen Shot**:", started=True)
        await pilot.pause()
        assert app._stream_text == "已成功执行:1. **Screen Shot**:"
        live = app.query_one("#live", Static)
        assert "已成功执行:1. **Screen Shot**:" in str(live.content)
        log = app.query_one("#transcript", RichLog)
        rendered = "\n".join(strip.text for strip in log.lines)
        assert "已成功执行" not in rendered
        app._flush_live_stream()
        await pilot.pause()
        rendered = "\n".join(strip.text for strip in log.lines)
        assert "已成功执行:1. **Screen Shot**:" in rendered
        assert rendered.count("已成功执行") == 1
        assert app._stream_text == ""


async def test_shift_enter_inserts_newline(settings: Settings) -> None:
    """Shift+Enter 插入换行且不提交。"""
    submitted: list[str] = []

    async def capture(raw: str) -> None:
        submitted.append(raw)

    app = MaxGuiApp(settings, force_new=True)
    app._handle_submit = capture  # type: ignore[method-assign]
    async with app.run_test() as pilot:
        prompt = app.query_one(PromptInput)
        prompt.text = "line"
        await pilot.press("shift+enter")
        await pilot.pause()
        assert submitted == []
        assert "\n" in prompt.text
