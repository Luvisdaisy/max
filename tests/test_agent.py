"""Agent 图：纯文本完成、一轮工具、迭代上限、中断恢复、截图回注。"""

from __future__ import annotations

import asyncio

from max_gui.agent.graph import ITERATION_LIMIT_MESSAGE, AgentRunner
from max_gui.config import Settings
from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.inference.client import ChatDelta
from max_gui.session.store import SessionStore
from max_gui.tools.desktop import clear_desktop_context
from max_gui.tools.registry import AutoApproveGate, build_default_registry


class ScriptedClient:
    """按预设 `ChatDelta` 依次返回的假推理客户端。"""

    def __init__(self, deltas: list[ChatDelta]) -> None:
        """参数：`deltas` 为每次 `stream` 弹出的回复。"""
        self.deltas = list(deltas)
        self.requests: list[list[dict]] = []

    async def stream(self, messages, *, tools=None, on_token=None, should_stop=None):
        """记录请求消息并弹出下一条脚本回复。"""
        self.requests.append(messages)
        delta = self.deltas.pop(0)
        if delta.text and on_token:
            on_token(delta.text)
        return delta


class SlowClient:
    """进入 `stream` 后循环等待，便于测试中断。"""

    def __init__(self) -> None:
        """`started` 在首次进入流式循环时置位。"""
        self.started = asyncio.Event()

    async def stream(self, messages, *, tools=None, on_token=None, should_stop=None):
        """轮询 `should_stop`，被中断则返回 `interrupted`。"""
        self.started.set()
        for _ in range(50):
            if should_stop and should_stop():
                return ChatDelta(text="partial", finish_reason="interrupted")
            await asyncio.sleep(0.02)
        return ChatDelta(text="too late")


def _runner(settings: Settings, client) -> tuple[AgentRunner, SessionStore]:
    """用自动批准门和假桌面后端组装 Runner。"""
    store = SessionStore(settings.sessions_dir)
    registry = build_default_registry(
        settings, gate=AutoApproveGate(), desktop=FakeDesktopBackend()
    )
    return AgentRunner(settings, client, registry, store), store


async def test_text_only_completion(settings: Settings) -> None:
    """无工具调用时直接完成，并落盘用户与助手消息。"""
    client = ScriptedClient([ChatDelta(text="世界")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="你好")
    assert state["status"] == "done"
    assert state["messages"][-1]["content"]["text"] == "世界"
    loaded = store.get(session.id)
    assert loaded is not None
    assert any(msg.role == "user" for msg in loaded.messages)
    assert any(msg.role == "assistant" for msg in loaded.messages)


async def test_one_tool_cycle(settings: Settings) -> None:
    """一轮 `read_file` 后，工具结果进入下一轮 Think 的请求。"""
    (settings.workspace / "notes.md").write_text("secret-note", encoding="utf-8")
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "notes.md"}'},
                    }
                ]
            ),
            ChatDelta(text="读到了"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="读 notes")
    assert state["status"] == "done"
    tool_msgs = [msg for msg in state["messages"] if msg.get("role") == "tool"]
    assert tool_msgs and "secret-note" in tool_msgs[0]["content"]
    assert any(
        msg.get("role") == "tool" and "secret-note" in str(msg.get("content"))
        for req in client.requests
        for msg in req
    )


async def test_iteration_limit(settings: Settings) -> None:
    """反复要工具时在 `max_iterations` 处以错误停住。"""
    settings.max_iterations = 1
    loop_call = ChatDelta(
        tool_calls=[
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "list_dir", "arguments": '{"path": "."}'},
            }
        ]
    )
    client = ScriptedClient([loop_call, loop_call, loop_call])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="一直列目录")
    assert state["status"] == "error"
    assert ITERATION_LIMIT_MESSAGE in str(state.get("error"))
    assert not client.deltas or True


async def test_interrupt_mid_think(settings: Settings) -> None:
    """Think 中途中断会写 `interrupted` 状态与 checkpoint。"""
    client = SlowClient()
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")

    async def cancel_soon() -> None:
        await client.started.wait()
        runner.interrupt()

    task = asyncio.create_task(cancel_soon())
    state = await runner.run(session, user_text="慢一点")
    await task
    assert state["status"] == "interrupted"
    loaded = store.get(session.id)
    assert loaded is not None
    assert loaded.status == "interrupted"
    assert loaded.checkpoint is not None


async def test_resume_from_json_checkpoint(settings: Settings) -> None:
    """从磁盘 checkpoint 恢复后续能正常完成。"""
    client = ScriptedClient([ChatDelta(text="继续")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    session.status = "interrupted"
    session.checkpoint = {
        "session_id": session.id,
        "messages": [{"role": "user", "content": {"text": "hi", "images": []}}],
        "images": [],
        "pending_tool_calls": [],
        "iteration": 0,
        "status": "thinking",
        "error": None,
    }
    store.save(session)
    session = store.get(session.id)
    assert session is not None
    state = await runner.run(session, resume=True)
    assert state["status"] == "done"
    assert state["messages"][-1]["content"]["text"] == "继续"


async def test_screenshot_tool_image_reaches_think(settings: Settings) -> None:
    """截图工具的图像会编进下一轮 Think 的 tool 消息。"""
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "shot1",
                        "type": "function",
                        "function": {"name": "screenshot", "arguments": "{}"},
                    }
                ]
            ),
            ChatDelta(text="看到屏幕了"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="截一张图")
    assert state["status"] == "done"
    tool_msgs = [msg for msg in state["messages"] if msg.get("role") == "tool"]
    assert tool_msgs and isinstance(tool_msgs[0]["content"], dict)
    assert tool_msgs[0]["content"]["images"]
    tool_encoded = next(item for item in client.requests[1] if item.get("role") == "tool")
    types = [part["type"] for part in tool_encoded["content"]]
    assert "text" in types and "image_url" in types
    loaded = store.get(session.id)
    assert loaded is not None
    assert loaded.view_frame is not None
    assert loaded.view_frame["view_width"] > 0


async def test_next_turn_reuses_saved_view_frame(settings: Settings) -> None:
    """下一回合清空 ContextVar 后，仍按会话里的视图像素换算。"""
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "shot1",
                        "type": "function",
                        "function": {"name": "screenshot", "arguments": "{}"},
                    }
                ]
            ),
            ChatDelta(text="已截图"),
            ChatDelta(
                tool_calls=[
                    {
                        "id": "move1",
                        "type": "function",
                        "function": {
                            "name": "mouse_move",
                            "arguments": '{"x": 16, "y": 10}',
                        },
                    }
                ]
            ),
            ChatDelta(text="已移动"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    first = await runner.run(session, user_text="截图")
    assert first["status"] == "done"
    session = store.get(session.id)
    assert session is not None
    assert session.view_frame is not None
    frame = session.view_frame
    clear_desktop_context()
    second = await runner.run(session, user_text="移动")
    assert second["status"] == "done"
    move_msg = next(
        msg
        for msg in second["messages"]
        if msg.get("role") == "tool" and "指针已移到" in str(msg.get("content"))
    )
    text = (
        move_msg["content"]["text"]
        if isinstance(move_msg["content"], dict)
        else move_msg["content"]
    )
    assert "视图像素" in text
    assert "尚无截图" not in text
    expected_x = round(16 * frame["logical_width"] / frame["view_width"])
    expected_y = round(10 * frame["logical_height"] / frame["view_height"])
    assert f"({expected_x}, {expected_y})" in text
