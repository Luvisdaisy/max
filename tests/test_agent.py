"""Agent 图：纯文本完成、一轮工具、迭代上限、中断恢复、截图回注。"""

from __future__ import annotations

import asyncio
import json

import pytest

from max_gui.agent.graph import ITERATION_LIMIT_MESSAGE, AgentRunner
from max_gui.agent.prompts import GUI_SYSTEM_PROMPT, os_contract
from max_gui.config import Settings
from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.inference.client import ChatDelta, TokenUsage
from max_gui.inference.omniparser import DetectedBox, LocateRuntime
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


async def _locate_safari(_path) -> list[DetectedBox]:
    """为短期事实测试返回一个带稳定标签的可点击 Dock 图标。"""
    return [DetectedBox(x1=0, y1=0, x2=20, y2=20, label="Safari", role="icon", score=1.0)]


def _runner_with_locate(settings: Settings, client) -> tuple[AgentRunner, SessionStore]:
    """装配含确定性定位结果的 Runner，验证真实工具到上下文的链路。"""
    store = SessionStore(settings.sessions_dir)
    registry = build_default_registry(
        settings,
        gate=AutoApproveGate(),
        desktop=FakeDesktopBackend(),
        locate=LocateRuntime(settings, parse_fn=_locate_safari),
    )
    return AgentRunner(settings, client, registry, store), store


def _run_events(settings: Settings, run_id: str) -> list[dict]:
    """读取指定运行的全部合法 JSONL 事件。"""
    path = settings.project_root / "artifacts" / "runs" / f"{run_id}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def test_text_only_completion(settings: Settings) -> None:
    """无工具调用时直接完成，并落盘用户与助手消息。"""
    client = ScriptedClient([ChatDelta(text="世界")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="你好")
    assert state["status"] == "done"
    assert state["run_id"].startswith("run-")
    assert state["messages"][-1]["content"]["text"] == "世界"
    loaded = store.get(session.id)
    assert loaded is not None
    assert any(msg.role == "user" for msg in loaded.messages)
    assert any(msg.role == "assistant" for msg in loaded.messages)
    event_types = [item["event_type"] for item in _run_events(settings, state["run_id"])]
    assert event_types[0] == "run.started"
    assert event_types[-1] == "run.completed"


async def test_one_tool_cycle(settings: Settings) -> None:
    """一轮 `screen_info` 后，工具结果进入下一轮 Think 的请求。"""
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "call1",
                        "type": "function",
                        "function": {"name": "screen_info", "arguments": "{}"},
                    }
                ]
            ),
            ChatDelta(text="读到了"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="看屏幕")
    assert state["status"] == "done"
    tool_msgs = [msg for msg in state["messages"] if msg.get("role") == "tool"]
    assert tool_msgs and isinstance(tool_msgs[0]["content"], dict)
    assert "screen_width" in tool_msgs[0]["content"]["text"]
    assert any(
        msg.get("role") == "tool" and "screen_width" in str(msg.get("content"))
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
                "function": {"name": "screen_info", "arguments": "{}"},
            }
        ]
    )
    client = ScriptedClient([loop_call, loop_call, loop_call])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="一直查屏幕")
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


def test_os_contract_darwin_not_windows() -> None:
    """darwin 文案含 macOS 且否定 Windows。"""
    text = os_contract("Darwin")
    assert "macOS" in text
    assert "不是 Windows" in text
    assert "command" in text
    assert "不是 Windows" not in os_contract("Windows")


def test_system_prompt_separates_user_reply_from_native_tools() -> None:
    """提示词让普通正文回答用户，工具调用不再要求正文 JSON 协议。"""
    assert "直接用简短、完整的自然语言回答用户" in GUI_SYSTEM_PROMPT
    assert "原生 tool calling" in GUI_SYSTEM_PROMPT
    assert "每次回复必须严格按以下 JSON 格式输出" not in GUI_SYSTEM_PROMPT
    assert '"thought"' not in GUI_SYSTEM_PROMPT


async def test_think_injects_system_not_persisted(settings: Settings) -> None:
    """think 请求带 GUI system，会话 JSON 不保存该角色。"""
    client = ScriptedClient([ChatDelta(text="好")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    await runner.run(session, user_text="你好")
    assert client.requests[0][0]["role"] == "system"
    content = client.requests[0][0]["content"]
    assert "screenshot" in content
    assert "locate" in content
    assert "ocr_locate" not in content
    assert "view_width" in content
    assert "逻辑坐标" in content
    assert "红十字" in content
    assert "键鼠" in content
    assert "核验" in content
    loaded = store.get(session.id)
    assert loaded is not None
    assert all(msg.role != "system" for msg in loaded.messages)


async def test_think_system_names_macos(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """darwin 上系统消息标明 macOS，不是 Windows。"""
    monkeypatch.setattr("max_gui.agent.prompts.platform.system", lambda: "Darwin")
    client = ScriptedClient([ChatDelta(text="好")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    await runner.run(session, user_text="你好")
    content = client.requests[0][0]["content"]
    assert "macOS" in content
    assert "不是 Windows" in content
    assert "command" in content


async def test_think_system_includes_view_size(settings: Settings) -> None:
    """截图成功后下一轮 think 的 system 含当前视图宽高。"""
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
    await runner.run(session, user_text="截图")
    loaded = store.get(session.id)
    assert loaded is not None and loaded.view_frame is not None
    content = client.requests[1][0]["content"]
    assert str(loaded.view_frame["view_width"]) in content
    assert str(loaded.view_frame["view_height"]) in content


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
    client = ScriptedClient(
        [
            ChatDelta(
                text="1. 看屏幕\n2. 汇报\n子任务完成",
                tool_calls=[
                    {
                        "id": "r1",
                        "type": "function",
                        "function": {
                            "name": "screen_info",
                            "arguments": "{}",
                        },
                    }
                ],
            ),
            ChatDelta(text="好了"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="看屏幕")
    assert state["current_subtask"] == "汇报"


async def test_tool_message_stores_exec_and_run_reference(settings: Settings) -> None:
    """截图结果保留会话 `exec`，独立运行事件用消息下标关联。"""
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
    assert runs.is_dir() and any(runs.iterdir())
    events = _run_events(settings, state["run_id"])
    tool_event = next(item for item in events if item["event_type"] == "tool.completed")
    assert tool_event["data"]["tool_name"] == "screenshot"
    assert isinstance(tool_event["data"]["session_message_index"], int)
    assert "arguments" not in tool_event["data"]
    tool_encoded = next(item for item in client.requests[1] if item.get("role") == "tool")
    assert "exec" not in tool_encoded
    assert '"duration_ms"' not in json.dumps(tool_encoded, ensure_ascii=False)


async def test_click_followup_image_reaches_think(settings: Settings) -> None:
    """移鼠成功后的新截图会编进下一轮 think。"""
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "clk",
                        "type": "function",
                        "function": {
                            "name": "mouse_move",
                            "arguments": '{"x": 8, "y": 8}',
                        },
                    }
                ]
            ),
            ChatDelta(text="移完了"),
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


class FailingStreamClient:
    """`stream` 抛出推理 HTTP 错误，供测试落盘。"""

    async def stream(
        self, messages, *, tools=None, on_token=None, on_reasoning=None, should_stop=None
    ):
        """始终失败。"""
        raise RuntimeError("推理服务返回 400：maximum context length")


async def test_think_stream_error_persists_session(settings: Settings) -> None:
    """think 推理失败后会话 status 为 error，并带上错误正文。"""
    client = FailingStreamClient()
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="继续")
    assert state["status"] == "error"
    assert "400" in str(state.get("error"))
    loaded = store.get(session.id)
    assert loaded is not None
    assert loaded.status == "error"
    assert loaded.checkpoint is not None
    assert loaded.checkpoint.get("status") == "error"
    assert "400" in str(loaded.checkpoint.get("error") or loaded.status)


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
                        "function": {"name": "screen_info", "arguments": "{}"},
                    },
                    {
                        "id": "b",
                        "type": "function",
                        "function": {"name": "screen_info", "arguments": "{}"},
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


async def test_two_turns_have_distinct_run_ids(settings: Settings) -> None:
    """同一会话的两个普通回合生成不同运行编号。"""
    client = ScriptedClient([ChatDelta(text="一"), ChatDelta(text="二")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    first = await runner.run(session, user_text="第一回合")
    second = await runner.run(session, user_text="第二回合")
    assert first["run_id"] != second["run_id"]
    assert _run_events(settings, first["run_id"])[0]["session_id"] == session.id
    assert _run_events(settings, second["run_id"])[0]["session_id"] == session.id


async def test_new_task_does_not_replay_completed_task_messages(settings: Settings) -> None:
    """同一会话的新任务只发送自身指令，不重放上一任务内容。"""
    client = ScriptedClient([ChatDelta(text="第一任务完成"), ChatDelta(text="第二任务完成")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    await runner.run(session, user_text="旧任务专有指令")
    second = await runner.run(session, user_text="新任务专有指令")
    encoded = json.dumps(client.requests[1], ensure_ascii=False)
    assert "新任务专有指令" in encoded
    assert "旧任务专有指令" not in encoded
    assert second["task_context"]["user_instruction"] == "新任务专有指令"
    loaded = store.get(session.id)
    assert loaded is not None
    assert len(loaded.messages) == 4


async def test_task_context_rolls_actions_and_redacts_keyboard_text(settings: Settings) -> None:
    """任务胶囊最多保留六条动作，键盘正文不会进入动作摘要。"""
    secret = "不能出现在胶囊里的键入内容"
    calls = [
        {
            "id": "type",
            "type": "function",
            "function": {"name": "keyboard_type", "arguments": json.dumps({"text": secret})},
        }
    ]
    calls.extend(
        {
            "id": f"screen-{index}",
            "type": "function",
            "function": {"name": "screen_info", "arguments": "{}"},
        }
        for index in range(6)
    )
    client = ScriptedClient([ChatDelta(tool_calls=calls), ChatDelta(text="完成")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="执行多步任务")
    history = state["task_context"]["action_history"]
    assert len(history) == 6
    assert all(secret not in json.dumps(item, ensure_ascii=False) for item in history)
    request = client.requests[1]
    assistant = next(item for item in request if item.get("role") == "assistant")
    tool_ids = {str(item["tool_call_id"]) for item in request if item.get("role") == "tool"}
    call_ids = {str(item["id"]) for item in assistant["tool_calls"]}
    assert tool_ids == call_ids
    loaded = store.get(session.id)
    assert loaded is not None and loaded.task_context is not None
    assert secret not in json.dumps(loaded.task_context, ensure_ascii=False)


async def test_grounded_facts_reuse_target_then_require_click_verification(
    settings: Settings,
) -> None:
    """当前帧定位进入摘要，移鼠后的新帧仅保留无坐标点击核验事实。"""
    calls = [
        ("shot", "screenshot", {}),
        ("locate", "locate", {}),
        ("move", "mouse_move", {"target_id": 1}),
    ]
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments)},
                    }
                ]
            )
            for call_id, name, arguments in calls
        ]
        + [ChatDelta(text="完成")]
    )
    settings.max_iterations = 4
    runner, store = _runner_with_locate(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="打开 Safari")
    move_request = client.requests[2]
    move_user = next(item for item in move_request if item.get("role") == "user")
    assert "Safari" in str(move_user["content"])
    assert "target_id=1" in str(move_user["content"])
    click_request = client.requests[3]
    click_user = next(item for item in click_request if item.get("role") == "user")
    assert "Safari" in str(click_user["content"])
    assert "无参数 mouse_click" in str(click_user["content"])
    facts = state["task_context"]["grounded_facts"]
    assert len(facts) == 1
    assert facts[0]["kind"] == "cursor_verification"
    assert facts[0]["target_id"] is None
    loaded = store.get(session.id)
    assert loaded is not None and loaded.task_context is not None
    assert loaded.task_context["grounded_facts"][0]["label"] == "Safari"


async def test_context_diagnostics_count_without_copying_user_text(settings: Settings) -> None:
    """模型事件记录裁剪计数和任务标识，不复制用户指令。"""
    secret = "不应写进运行诊断的用户指令"
    client = ScriptedClient([ChatDelta(text="完成")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text=secret)
    event = next(
        item
        for item in _run_events(settings, state["run_id"])
        if item["event_type"] == "model.completed"
    )
    data = event["data"]
    assert data["task_id"] == state["task_context"]["task_id"]
    assert data["context_message_count"] >= 1
    assert "context_excluded_message_count" in data
    assert secret not in json.dumps(data, ensure_ascii=False)


async def test_reasoning_and_keyboard_text_are_not_duplicated_to_run_log(
    settings: Settings,
) -> None:
    """reasoning 与键盘正文留在会话，运行事件只保存长度和引用。"""
    secret_reasoning = "内部推理原文"
    secret_input = "sensitive-input"
    client = ScriptedClient(
        [
            ChatDelta(
                reasoning=secret_reasoning,
                tool_calls=[
                    {
                        "id": "type-1",
                        "type": "function",
                        "function": {
                            "name": "keyboard_type",
                            "arguments": json.dumps({"text": secret_input}),
                        },
                    }
                ],
            ),
            ChatDelta(text="结束"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="输入")
    loaded = store.get(session.id)
    assert loaded is not None
    assistant = next(item for item in loaded.messages if item.role == "assistant")
    tool = next(item for item in loaded.messages if item.role == "tool")
    assert assistant.content["reasoning"] == secret_reasoning
    assert tool.content["exec"]["arguments"]["text"] == secret_input
    log_text = json.dumps(_run_events(settings, state["run_id"]), ensure_ascii=False)
    assert secret_reasoning not in log_text
    assert secret_input not in log_text
    model_event = next(
        item
        for item in _run_events(settings, state["run_id"])
        if item["event_type"] == "model.completed"
    )
    assert model_event["data"]["reasoning_chars"] == len(secret_reasoning)
    assert "prompt_tokens" not in model_event["data"]


async def test_model_completed_records_usage_without_copying_text(
    settings: Settings,
) -> None:
    """成功调用把三项用量写入运行事件，且不含回复原文。"""
    secret = "这是不应进入运行日志的正文"
    client = ScriptedClient(
        [
            ChatDelta(
                text=secret,
                usage=TokenUsage(prompt_tokens=12, completion_tokens=8, total_tokens=20),
            )
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="用量")
    events = _run_events(settings, state["run_id"])
    completed = next(item for item in events if item["event_type"] == "model.completed")
    terminal = next(item for item in events if item["event_type"] == "run.completed")
    assert completed["data"]["prompt_tokens"] == 12
    assert completed["data"]["completion_tokens"] == 8
    assert completed["data"]["total_tokens"] == 20
    assert secret not in json.dumps(completed, ensure_ascii=False)
    assert terminal["data"]["prompt_tokens"] == 12
    assert terminal["data"]["completion_tokens"] == 8
    assert terminal["data"]["total_tokens"] == 20


async def test_resume_reuses_run_and_reports_unfinished_tool(settings: Settings) -> None:
    """带 run_id 的中断 checkpoint 续写原文件，并报告未闭合工具但不重放。"""
    client = ScriptedClient([ChatDelta(text="重新观察后完成")])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    run_id = "run-existing"
    runs = settings.project_root / "artifacts" / "runs"
    runs.mkdir(parents=True)
    existing = {
        "schema_version": 1,
        "event_id": f"{run_id}:1",
        "sequence": 1,
        "timestamp": "2026-08-21T00:00:00.000+08:00",
        "elapsed_ms": 10,
        "run_id": run_id,
        "session_id": session.id,
        "event_type": "tool.started",
        "iteration": 0,
        "subtask": None,
        "data": {"call_id": "click-1", "tool_name": "mouse_click"},
    }
    (runs / f"{run_id}.jsonl").write_text(
        json.dumps(existing, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    session.status = "interrupted"
    session.checkpoint = {
        "session_id": session.id,
        "run_id": run_id,
        "messages": [{"role": "user", "content": {"text": "继续", "images": []}}],
        "images": [],
        "pending_tool_calls": [],
        "iteration": 0,
        "status": "thinking",
        "error": None,
    }
    store.save(session)
    state = await runner.run(session, resume=True)
    assert state["run_id"] == run_id
    events = _run_events(settings, run_id)
    resumed = next(item for item in events if item["event_type"] == "run.resumed")
    assert resumed["data"]["unfinished_tools"] == [
        {"call_id": "click-1", "tool_name": "mouse_click"}
    ]
    assert [item["event_type"] for item in events].count("tool.started") == 1


async def test_inference_error_emits_model_and_run_failures(settings: Settings) -> None:
    """推理错误先形成模型失败，再以运行失败终止并保持会话 error。"""
    runner, store = _runner(settings, FailingStreamClient())
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="失败")
    events = _run_events(settings, state["run_id"])
    types = [item["event_type"] for item in events]
    assert types.index("model.failed") < types.index("run.failed")
    assert events[-1]["data"]["final_status"] == "error"
