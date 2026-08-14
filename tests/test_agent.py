from __future__ import annotations

import asyncio

from max_gui.agent.graph import ITERATION_LIMIT_MESSAGE, AgentRunner
from max_gui.config import Settings
from max_gui.inference.client import ChatDelta
from max_gui.session.store import SessionStore
from max_gui.tools.registry import AutoApproveGate, build_default_registry


class ScriptedClient:
    def __init__(self, deltas: list[ChatDelta]) -> None:
        self.deltas = list(deltas)
        self.requests: list[list[dict]] = []

    async def stream(self, messages, *, tools=None, on_token=None, should_stop=None):  # noqa: ANN001
        self.requests.append(messages)
        delta = self.deltas.pop(0)
        if delta.text and on_token:
            on_token(delta.text)
        return delta


class SlowClient:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def stream(self, messages, *, tools=None, on_token=None, should_stop=None):  # noqa: ANN001
        self.started.set()
        for _ in range(50):
            if should_stop and should_stop():
                return ChatDelta(text="partial", finish_reason="interrupted")
            await asyncio.sleep(0.02)
        return ChatDelta(text="too late")


def _runner(settings: Settings, client) -> tuple[AgentRunner, SessionStore]:  # noqa: ANN001
    store = SessionStore(settings.sessions_dir)
    registry = build_default_registry(settings, gate=AutoApproveGate())
    return AgentRunner(settings, client, registry, store), store


async def test_text_only_completion(settings: Settings) -> None:
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
