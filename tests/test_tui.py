"""TUI：斜杠命令、附件、会话恢复、Enter 发送与流式单条消息。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from PIL import Image
from textual.widgets import RichLog, Static

from max_gui.app import MaxGuiApp
from max_gui.config import Settings
from max_gui.observability import RunEvent
from max_gui.session.store import SessionMessage, SessionStore
from max_gui.widgets.prompt import PromptInput


def _event(event_type: str, *, data: dict | None = None, elapsed_ms: int = 10) -> RunEvent:
    """构造 TUI 测试使用的固定运行事件。"""
    return RunEvent(
        event_id=f"run-monitor:{event_type}",
        sequence=1,
        timestamp="2026-08-21T00:00:00.000+08:00",
        elapsed_ms=elapsed_ms,
        run_id="run-monitor",
        session_id="session-monitor",
        event_type=event_type,  # type: ignore[arg-type]
        iteration=2,
        subtask="填写表单",
        data=data or {},
    )


async def test_unknown_command_does_not_call_model(settings: Settings) -> None:
    """未知斜杠命令不启动回合。"""
    app = MaxGuiApp(settings, force_new=True)
    async with app.run_test() as pilot:
        await app._handle_command("/not-a-command")
        assert app._turn_active is False
        await pilot.pause()


async def test_model_command_is_unknown(settings: Settings) -> None:
    """`/model` 按未知命令处理，不改变当前模型。"""
    app = MaxGuiApp(settings, force_new=True)
    async with app.run_test() as pilot:
        await app._handle_command("/model qwen3.5-4b")
        assert app.settings.model_name == "qwen3.5-2b"
        log = app.query_one("#transcript", RichLog)
        rendered = "\n".join(strip.text for strip in log.lines)
        assert "未知命令" in rendered
        await app._handle_command("/model")
        rendered = "\n".join(strip.text for strip in log.lines)
        assert rendered.count("未知命令") >= 2
        await pilot.pause()


async def test_switch_session_keeps_configured_model(settings: Settings) -> None:
    """切换旧会话不覆盖 `.env` 里的模型名。"""
    store = SessionStore(settings.sessions_dir)
    old = store.create(model="2b")
    store.append_messages(
        old, [SessionMessage(role="user", content={"text": "旧会话", "images": []})]
    )
    app = MaxGuiApp(settings, force_new=True)
    async with app.run_test() as pilot:
        assert app.settings.model_name == "qwen3.5-2b"
        await app._handle_command(f"/sessions {old.id}")
        assert app.session is not None
        assert app.session.id == old.id
        assert app.settings.model_name == "qwen3.5-2b"
        assert app.runner is not None
        assert app.runner.settings.model_name == "qwen3.5-2b"
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
    """流式 token 先聚在记录框内的 `#live`，flush 后只写入一条历史。"""
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
        assert live.parent is not None and live.parent.id == "record"
        assert app.query_one("#transcript").parent is live.parent
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


def _transcript(app: MaxGuiApp) -> str:
    """记录区纯文本。"""
    log = app.query_one("#transcript", RichLog)
    return "\n".join(strip.text for strip in log.lines)


async def test_live_reasoning_and_commit_two_thinks(settings: Settings) -> None:
    """思考进 live；两轮 think 落成两条助手；工具在回合内可见；状态含执行工具。"""
    app = MaxGuiApp(settings, force_new=True)
    recorded: list[str] = []
    async with app.run_test() as pilot:
        real_status = app._set_status

        def capture_status(text: str) -> None:
            recorded.append(text)
            real_status(text)

        app._set_status = capture_status  # type: ignore[method-assign]

        async def fake_run(*_args, **kwargs):
            on_status = kwargs.get("on_status")
            on_token = kwargs.get("on_token")
            on_reasoning = kwargs.get("on_reasoning")
            on_message = kwargs.get("on_message")
            if on_status:
                on_status("thinking")
            if on_reasoning:
                on_reasoning("先截图")
            if on_token:
                on_token("调用工具")
            if on_message:
                on_message(
                    "assistant",
                    {"text": "调用工具", "reasoning": "先截图", "tool_calls": []},
                )
            if on_status:
                on_status("acting")
            if on_message:
                on_message("tool", {"text": "已单击left (1, 2)"})
            if on_status:
                on_status("thinking")
            if on_token:
                on_token("完成了")
            if on_message:
                on_message("assistant", {"text": "完成了"})
            return {
                "status": "done",
                "messages": [
                    {"role": "assistant", "content": {"text": "调用工具", "reasoning": "先截图"}},
                    {"role": "tool", "content": {"text": "已单击left (1, 2)"}},
                    {"role": "assistant", "content": {"text": "完成了"}},
                ],
            }

        assert app.runner is not None
        app.runner.run = fake_run  # type: ignore[method-assign]
        await app._handle_submit("点微信")
        await pilot.pause()
        live = app.query_one("#live", Static)
        assert app._stream_text == ""
        assert str(live.content) in {"", "None"} or not live.display
        rendered = _transcript(app)
        assert "先截图" in rendered
        assert rendered.count("调用工具") == 1
        assert "已单击left (1, 2)" in rendered
        assert "完成了" in rendered
        assistant_lines = [line for line in rendered.splitlines() if "助手" in line]
        assert len(assistant_lines) >= 2
        assert any("执行工具" in item for item in recorded)


async def test_restore_shows_reasoning(settings: Settings) -> None:
    """恢复会话时展示思考字段；无该字段的旧消息只显示正文。"""
    store = SessionStore(settings.sessions_dir)
    session = store.create(model="qwen3.5-2b")
    store.append_messages(
        session,
        [
            SessionMessage(role="user", content={"text": "hi", "images": []}),
            SessionMessage(
                role="assistant",
                content={"text": "你好", "reasoning": "这是问候"},
            ),
            SessionMessage(role="assistant", content={"text": "旧回复"}),
        ],
    )
    app = MaxGuiApp(settings, force_new=False)
    async with app.run_test() as pilot:
        rendered = _transcript(app)
        assert "这是问候" in rendered
        assert "你好" in rendered
        assert "旧回复" in rendered
        await pilot.pause()


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


async def test_turn_status_does_not_mention_runs(settings: Settings) -> None:
    """回合开始时状态区不指向 artifacts/runs。"""
    app = MaxGuiApp(settings, force_new=True)
    recorded: list[str] = []
    async with app.run_test() as pilot:
        real = app._set_status

        def capture(text: str) -> None:
            recorded.append(text)
            real(text)

        app._set_status = capture  # type: ignore[method-assign]

        async def fake_run(*_args, **_kwargs):
            return {
                "status": "done",
                "messages": [{"role": "assistant", "content": {"text": "好"}}],
            }

        assert app.runner is not None
        app.runner.run = fake_run  # type: ignore[method-assign]
        await app._handle_submit("打开计算器")
        await pilot.pause()
        assert any("思考中" in item for item in recorded)
        assert all("artifacts/runs/" not in item for item in recorded)


async def test_monitor_panel_is_visible_by_default(settings: Settings) -> None:
    """应用启动后独立监控面板默认可见并显示就绪。"""
    app = MaxGuiApp(settings, force_new=True)
    async with app.run_test() as pilot:
        monitor = app.query_one("#monitor", Static)
        assert monitor.display
        assert "运行监控（本机）" in str(monitor.content)
        assert "就绪" in str(monitor.content)
        assert "用量：未知" in str(monitor.content)
        assert "输入 0" not in str(monitor.content)
        assert monitor.parent is not app.query_one("#transcript").parent
        await pilot.pause()


async def test_tool_started_updates_monitor_before_runner_returns(settings: Settings) -> None:
    """工具开始事件在假 Runner 返回前更新面板，且不污染会话记录区。"""
    app = MaxGuiApp(settings, force_new=True)
    gate = asyncio.Event()
    async with app.run_test() as pilot:

        async def fake_run(*_args, **kwargs):
            on_event = kwargs.get("on_event")
            if on_event:
                on_event(
                    _event(
                        "tool.started",
                        data={
                            "tool_name": "keyboard_type",
                            "argument_chars": 99,
                            "text": "绝不能显示的键盘正文",
                        },
                    )
                )
            await gate.wait()
            return {"status": "done", "messages": []}

        assert app.runner is not None
        app.runner.run = fake_run  # type: ignore[method-assign]
        task = asyncio.create_task(app._handle_submit("填写"))
        await pilot.pause()
        rendered = str(app.query_one("#monitor", Static).content)
        assert "keyboard_type" in rendered
        assert "绝不能显示的键盘正文" not in rendered
        assert "keyboard_type" not in _transcript(app)
        gate.set()
        await task
        await pilot.pause()


async def test_terminal_summary_and_recorder_failure_stay_in_monitor(
    settings: Settings,
) -> None:
    """终态统计和写入诊断显示在面板，不作为对话消息。"""
    app = MaxGuiApp(settings, force_new=True)
    async with app.run_test() as pilot:
        app._handle_run_event(_event("run.started"))
        app._handle_run_event(
            _event(
                "run.completed",
                elapsed_ms=1234,
                data={
                    "final_status": "done",
                    "model_duration_ms": 800,
                    "tool_duration_ms": 300,
                    "tool_successes": 2,
                    "tool_failures": 1,
                },
            )
        )
        app._handle_run_event(
            _event(
                "recorder.failed",
                data={
                    "message": "运行日志写入失败",
                    "error": "/private/secret/path 不可写",
                },
            )
        )
        rendered = str(app.query_one("#monitor", Static).content)
        assert "完成" in rendered
        assert "800ms" in rendered
        assert "300ms" in rendered
        assert "2/1" in rendered
        assert "运行日志写入失败" in rendered
        assert "/private/secret/path" not in rendered
        assert "运行日志写入失败" not in _transcript(app)
        await pilot.pause()


async def test_monitor_shows_token_usage_and_does_not_double_count(
    settings: Settings,
) -> None:
    """面板累计用量、最近事件含当次输入输出；终态覆盖避免加两遍；记录区无用量行。"""
    app = MaxGuiApp(settings, force_new=True)
    async with app.run_test() as pilot:
        app._handle_run_event(_event("run.started"))
        app._handle_run_event(
            _event(
                "model.completed",
                data={
                    "duration_ms": 820,
                    "prompt_tokens": 12,
                    "completion_tokens": 8,
                    "total_tokens": 20,
                },
            )
        )
        rendered = str(app.query_one("#monitor", Static).content)
        assert "用量：输入 12 / 输出 8 / 合计 20" in rendered
        assert "输入 12" in rendered and "输出 8" in rendered
        assert "用量：未知" not in rendered
        assert "用量：输入 12" not in _transcript(app)
        app._handle_run_event(
            _event(
                "run.completed",
                data={
                    "final_status": "done",
                    "model_duration_ms": 820,
                    "tool_duration_ms": 0,
                    "tool_successes": 0,
                    "tool_failures": 0,
                    "prompt_tokens": 12,
                    "completion_tokens": 8,
                    "total_tokens": 20,
                },
            )
        )
        rendered = str(app.query_one("#monitor", Static).content)
        assert "用量：输入 12 / 输出 8 / 合计 20" in rendered
        assert "用量：输入 24" not in rendered
        await pilot.pause()


async def test_monitor_unknown_usage_is_not_zero(settings: Settings) -> None:
    """模型完成但无用量时面板仍为未知，最近事件写用量未知。"""
    app = MaxGuiApp(settings, force_new=True)
    async with app.run_test() as pilot:
        app._handle_run_event(_event("run.started"))
        app._handle_run_event(_event("model.completed", data={"duration_ms": 10}))
        rendered = str(app.query_one("#monitor", Static).content)
        assert "用量：未知" in rendered
        assert "输入 0 / 输出 0" not in rendered
        assert "用量未知" in rendered
        await pilot.pause()
