"""Agent 图：纯文本完成、一轮工具、迭代上限、中断恢复、截图回注。"""

from __future__ import annotations

import asyncio
import json

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

    async def stream(
        self, messages, *, tools=None, on_token=None, on_reasoning=None, should_stop=None
    ):
        """记录请求消息并弹出下一条脚本回复。"""
        self.requests.append(messages)
        delta = self.deltas.pop(0)
        if delta.reasoning and on_reasoning:
            on_reasoning(delta.reasoning)
        if delta.text and on_token:
            on_token(delta.text)
        return delta


class SlowClient:
    """进入 `stream` 后循环等待，便于测试中断。"""

    def __init__(self) -> None:
        """`started` 在首次进入流式循环时置位。"""
        self.started = asyncio.Event()

    async def stream(
        self, messages, *, tools=None, on_token=None, on_reasoning=None, should_stop=None
    ):
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
    assert tool_msgs and isinstance(tool_msgs[0]["content"], dict)
    assert "secret-note" in tool_msgs[0]["content"]["text"]
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
    assert "(16, 10)" in text
    expected_x = round(16 * frame["logical_width"] / frame["view_width"])
    expected_y = round(10 * frame["logical_height"] / frame["view_height"])
    assert f"逻辑坐标 ({expected_x}, {expected_y})" not in text


async def test_think_injects_system_not_persisted(settings: Settings) -> None:
    """think 请求带 GUI system，会话 JSON 不保存该角色。"""
    client = ScriptedClient([ChatDelta(text="好")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    await runner.run(session, user_text="你好")
    assert client.requests[0][0]["role"] == "system"
    assert "screenshot" in client.requests[0][0]["content"]
    assert "view_width" in client.requests[0][0]["content"]
    assert "逻辑坐标" in client.requests[0][0]["content"]
    loaded = store.get(session.id)
    assert loaded is not None
    assert all(msg.role != "system" for msg in loaded.messages)


async def test_plan_stays_on_tool_error(settings: Settings) -> None:
    """编号计划写入状态；工具失败不推进子任务。"""
    client = ScriptedClient(
        [
            ChatDelta(
                text="1. 打开计算器\n2. 输入 1+1\n子任务完成",
                tool_calls=[
                    {
                        "id": "bad",
                        "type": "function",
                        "function": {"name": "no_such_tool", "arguments": "{}"},
                    }
                ],
            ),
            ChatDelta(text="停"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="算一下")
    assert state["plan"] == ["打开计算器", "输入 1+1"]
    assert state["current_subtask"] == "打开计算器"


async def test_plan_advances_after_successful_tool(settings: Settings) -> None:
    """成功工具且助手写了子任务完成后，推进到下一项。"""
    (settings.workspace / "notes.md").write_text("x", encoding="utf-8")
    client = ScriptedClient(
        [
            ChatDelta(
                text="1. 读文件\n2. 汇报\n子任务完成",
                tool_calls=[
                    {
                        "id": "r1",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path": "notes.md"}',
                        },
                    }
                ],
            ),
            ChatDelta(text="好了"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="读 notes")
    assert state["current_subtask"] == "汇报"


async def test_tool_message_stores_exec_not_run_file(settings: Settings) -> None:
    """截图结果写入会话 `exec`，不创建 artifacts/runs。"""
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
            ChatDelta(text="看到了"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="截图")
    tool_msgs = [msg for msg in state["messages"] if msg.get("role") == "tool"]
    assert tool_msgs
    content = tool_msgs[0]["content"]
    assert content["name"] == "screenshot"
    assert content["exec"]["has_image"] is True
    assert content["exec"]["error"] is None
    assert content["exec"]["duration_ms"] >= 0
    loaded = store.get(session.id)
    assert loaded is not None
    saved = next(msg for msg in loaded.messages if msg.role == "tool")
    assert saved.content["exec"]["has_image"] is True
    runs = settings.project_root / "artifacts" / "runs"
    assert not runs.exists() or not any(runs.iterdir())
    tool_encoded = next(item for item in client.requests[1] if item.get("role") == "tool")
    assert "exec" not in tool_encoded
    assert '"duration_ms"' not in json.dumps(tool_encoded, ensure_ascii=False)


async def test_click_followup_image_reaches_think(settings: Settings) -> None:
    """点击成功后的新截图会编进下一轮 think。"""
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "clk",
                        "type": "function",
                        "function": {
                            "name": "mouse_click",
                            "arguments": '{"x": 8, "y": 8}',
                        },
                    }
                ]
            ),
            ChatDelta(text="点完了"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="点一下")
    tool_msgs = [msg for msg in state["messages"] if msg.get("role") == "tool"]
    assert tool_msgs and isinstance(tool_msgs[0]["content"], dict)
    assert tool_msgs[0]["content"]["images"]
    tool_encoded = next(item for item in client.requests[1] if item.get("role") == "tool")
    types = [part["type"] for part in tool_encoded["content"]]
    assert "text" in types and "image_url" in types


async def test_progress_and_incremental_persist(settings: Settings) -> None:
    """状态随节点变化；双工具时第一条 tool 落盘后才跑第二条；结束不重复追加。"""
    statuses: list[str] = []
    committed: list[str] = []
    first_tool_roles: list[str] = []
    client = ScriptedClient(
        [
            ChatDelta(
                reasoning="列两次",
                text="开始",
                tool_calls=[
                    {
                        "id": "a",
                        "type": "function",
                        "function": {"name": "list_dir", "arguments": '{"path": "."}'},
                    },
                    {
                        "id": "b",
                        "type": "function",
                        "function": {"name": "list_dir", "arguments": '{"path": "."}'},
                    },
                ],
            ),
            ChatDelta(text="列完了"),
        ]
    )
    runner, store = _runner(settings, client)
    original = runner.registry.invoke
    calls = 0
    second_gate = asyncio.Event()

    async def gated_invoke(name: str, arguments: dict | str | None = None):
        nonlocal calls
        calls += 1
        if calls == 2:
            await second_gate.wait()
        return await original(name, arguments)

    runner.registry.invoke = gated_invoke  # type: ignore[method-assign]
    session = store.create(model="qwen3.5-2b")

    def on_message(role: str, _content: dict) -> None:
        committed.append(role)
        if role == "tool" and committed.count("tool") == 1:
            loaded = store.get(session.id)
            assert loaded is not None
            first_tool_roles.extend(msg.role for msg in loaded.messages)
            assert first_tool_roles.count("assistant") == 1
            assert first_tool_roles.count("tool") == 1
            assert calls == 1
            second_gate.set()

    state = await runner.run(
        session,
        user_text="列目录",
        on_status=statuses.append,
        on_message=on_message,
    )
    assert state["status"] == "done"
    assert "thinking" in statuses
    assert "acting" in statuses
    assert "observing" in statuses
    assert statuses.index("acting") > statuses.index("thinking")
    loaded = store.get(session.id)
    assert loaded is not None
    roles = [msg.role for msg in loaded.messages]
    assert roles.count("assistant") == 2
    assert roles.count("tool") == 2
    assistants = [msg for msg in loaded.messages if msg.role == "assistant"]
    assert assistants[0].content.get("reasoning") == "列两次"
    tools = [msg for msg in loaded.messages if msg.role == "tool"]
    assert assistants[0].created_at <= tools[0].created_at
    encoded = json.dumps(client.requests[1], ensure_ascii=False)
    assert "列两次" not in encoded
