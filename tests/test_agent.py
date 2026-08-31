"""Agent 图：纯文本完成、一轮工具、迭代上限、中断恢复、截图回注。"""

from __future__ import annotations

import asyncio
import json

import pytest

from max_gui.agent.context import grounded_facts_message, new_task_context
from max_gui.agent.graph import (
    ITERATION_LIMIT_MESSAGE,
    AgentRunner,
    _completion_evidence_ready,
    _update_recovery_after_observation,
)
from max_gui.agent.prompts import GUI_SYSTEM_PROMPT, os_contract
from max_gui.config import Settings
from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.desktop.ui_backends import FakeMacOSAXBackend
from max_gui.inference.client import ChatDelta, InferenceRequestError, TokenUsage
from max_gui.inference.retry import RetryMetadata, RetryNotice
from max_gui.session.store import SessionStore
from max_gui.tools.desktop import clear_desktop_context
from max_gui.tools.registry import AutoApproveGate, build_default_registry
from max_gui.ui import UIElement


class ScriptedClient:
    """按预设 `ChatDelta` 依次返回的假推理客户端。"""

    def __init__(self, deltas: list[ChatDelta]) -> None:
        """参数：`deltas` 为每次 `stream` 弹出的回复。"""
        self.deltas = list(deltas)
        self.requests: list[list[dict]] = []
        self.tool_requests: list[list[dict]] = []

    async def stream(
        self,
        messages,
        *,
        tools=None,
        on_token=None,
        on_reasoning=None,
        should_stop=None,
        on_retry=None,
    ):
        """记录请求消息并弹出下一条脚本回复。"""
        self.requests.append(messages)
        self.tool_requests.append(list(tools or []))
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
        self,
        messages,
        *,
        tools=None,
        on_token=None,
        on_reasoning=None,
        should_stop=None,
        on_retry=None,
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
    assert state["status"] == "done", state
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


async def test_dynamic_tool_schemas_follow_observation_stage(settings: Settings) -> None:
    """启动预观察后立即提供截图与视觉后备工具。"""
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "shot",
                        "type": "function",
                        "function": {"name": "screenshot", "arguments": "{}"},
                    }
                ]
            ),
            ChatDelta(text="已观察"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="看屏幕")
    assert state["status"] == "done"
    initial = {item["function"]["name"] for item in client.tool_requests[0]}
    observed = {item["function"]["name"] for item in client.tool_requests[1]}
    assert "screenshot" in initial
    assert "mouse_move" in initial
    assert "task_complete" not in initial
    assert "mouse_move" in observed
    assert "task_complete" not in observed
    move_schema = next(
        item for item in client.tool_requests[1] if item["function"]["name"] == "mouse_move"
    )
    assert "target_id" not in move_schema["function"]["parameters"]["properties"]


async def test_agent_runner_dispatches_ax_element_and_refreshes_observation(
    settings: Settings,
) -> None:
    """当前前台 Chrome 的 AX 快照让 Agent 分派点击，并在动作后附加新截图。"""
    ax = FakeMacOSAXBackend(elements=[_native_button(name="继续", app_id="chrome")])
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "click",
                        "type": "function",
                        "function": {
                            "name": "click",
                            "arguments": (
                                '{"element_id":"e_1","ui_version":1,'
                                '"intent":"点击继续",'
                                '"expectation":{"kind":"screen_changed"}}'
                            ),
                        },
                    }
                ]
            ),
            ChatDelta(
                tool_calls=[
                    {
                        "id": "done",
                        "type": "function",
                        "function": {
                            "name": "task_complete",
                            "arguments": '{"summary":"已点击","evidence":"后置截图已获取"}',
                        },
                    }
                ]
            ),
        ]
    )
    store = SessionStore(settings.sessions_dir)
    runner = AgentRunner(
        settings,
        client,
        build_default_registry(
            settings,
            gate=AutoApproveGate(),
            desktop=FakeDesktopBackend(),
            macos_ax=ax,
        ),
        store,
    )
    state = await runner.run(store.create(model="qwen3.5-2b"), user_text="点击继续")
    assert state["task_context"].get("ui_snapshot"), state["task_context"]
    initial_tools = {item["function"]["name"] for item in client.tool_requests[0]}
    assert "click" in initial_tools, initial_tools
    assert "mouse_move" in initial_tools, initial_tools
    assert "mouse_click" in initial_tools, initial_tools
    click_schema = next(
        item for item in client.tool_requests[0] if item["function"]["name"] == "click"
    )
    assert "intent" in click_schema["function"]["parameters"]["properties"]
    assert state["status"] == "done", state
    assert ax.calls == [("press", "e_1")]
    history = state["task_context"]["action_history"]
    assert history[0]["intent"] == "点击继续"
    click_result = next(item for item in state["messages"] if item.get("tool_call_id") == "click")
    assert click_result["content"]["images"]


async def test_chrome_ax_snapshot_uses_native_context(settings: Settings) -> None:
    """日常 Chrome 的 AX 控件生成 native 快照，不连接网页 DOM。"""
    ax = FakeMacOSAXBackend(elements=[_native_button()])
    store = SessionStore(settings.sessions_dir)
    runner = AgentRunner(
        settings,
        ScriptedClient([]),
        build_default_registry(settings, gate=AutoApproveGate(), macos_ax=ax),
        store,
    )
    context = await runner._replace_structured_ui_snapshot(
        new_task_context("上传文件"),
        frame_path="picker.png",
        desktop_observation={
            "active_app": {"id": "44", "name": "Google Chrome", "role": "application"},
            "active_dialog": {},
        },
    )
    assert context["ui_snapshot"]["context"] == "native"
    assert context["ui_snapshot"]["elements"][0]["backend"] == "macos_ax"


def _native_button(*, name: str = "打开", app_id: str = "44") -> UIElement:
    """构造原生文件选择器的最小 AX 按钮元素。"""
    return UIElement(
        id="",
        role="button",
        name=name,
        text=None,
        visible=True,
        enabled=True,
        editable=False,
        focused=False,
        app_id=app_id,
        window_id="picker",
        backend="macos_ax",
        locator={"fake": True},
    )


async def test_one_side_effect_per_response_pairs_all_tool_calls(settings: Settings) -> None:
    """同一模型回复只执行首个副作用，其余调用仍返回配对错误。"""
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "shot",
                        "type": "function",
                        "function": {"name": "screenshot", "arguments": "{}"},
                    }
                ]
            ),
            ChatDelta(
                tool_calls=[
                    {
                        "id": "move",
                        "type": "function",
                        "function": {
                            "name": "mouse_move",
                            "arguments": '{"x":8,"y":8}',
                        },
                    },
                    {
                        "id": "type",
                        "type": "function",
                        "function": {
                            "name": "keyboard_type",
                            "arguments": '{"text":"blocked"}',
                        },
                    },
                ]
            ),
            ChatDelta(
                tool_calls=[
                    {
                        "id": "done",
                        "type": "function",
                        "function": {
                            "name": "task_complete",
                            "arguments": '{"summary":"已移动","evidence":"光标截图可见"}',
                        },
                    }
                ]
            ),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="移动并输入")
    paired = {
        item["tool_call_id"]: item["content"]
        for item in state["messages"]
        if item.get("role") == "tool" and item.get("tool_call_id") in {"move", "type"}
    }
    assert set(paired) == {"move", "type"}
    assert paired["move"]["exec"]["code"] == "ok"
    assert paired["type"]["exec"]["code"] == "action_batch_blocked"
    assert "只提交一个副作用调用" in paired["type"]["text"]
    assert "动作后的截图" in paired["type"]["text"]


def test_action_batch_blocked_recovery_counts_one_per_response() -> None:
    """同一回复的多条批次阻断只累计一次，截图可清除护栏。"""
    context = new_task_context("测试批次恢复")
    blocked_batch = [
        {
            "name": "mouse_click",
            "content": {"text": "已阻断", "exec": {"code": "action_batch_blocked"}},
        },
        {
            "name": "keyboard_type",
            "content": {"text": "已阻断", "exec": {"code": "action_batch_blocked"}},
        },
    ]
    context = _update_recovery_after_observation(context, blocked_batch)
    assert context["recovery"]["failure_count"] == 1
    assert "只提交一个副作用调用" in str(context["recovery"]["recovery_hint"])
    context = _update_recovery_after_observation(context, blocked_batch)
    assert context["recovery"]["failure_count"] == 2
    context = _update_recovery_after_observation(
        context,
        [{"name": "screenshot", "content": {"text": "截图成功", "exec": {"ok": True}}}],
    )
    assert context["recovery"]["failure_count"] == 0


async def test_repeated_action_batches_end_with_recovery_exhausted(settings: Settings) -> None:
    """模型连续重复多副作用批次时在恢复阈值内终止，而不是耗尽迭代。"""
    settings.max_iterations = 4
    duplicate_batch = [
        {
            "id": "move",
            "type": "function",
            "function": {"name": "mouse_move", "arguments": '{"x":8,"y":8}'},
        },
        {
            "id": "click",
            "type": "function",
            "function": {"name": "mouse_click", "arguments": "{}"},
        },
    ]
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "shot",
                        "type": "function",
                        "function": {"name": "screenshot", "arguments": "{}"},
                    }
                ]
            ),
            ChatDelta(tool_calls=duplicate_batch),
            ChatDelta(tool_calls=duplicate_batch),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="移动并点击")
    assert state["status"] == "error"
    assert state["error"] == "recovery_exhausted"
    assert state["iteration"] == 3
    loaded = store.get(session.id)
    assert loaded is not None
    events = _run_events(settings, state["run_id"])
    assert events[-1]["event_type"] == "run.failed"
    assert events[-1]["data"]["terminal_reason"] == "recovery_exhausted"


def test_grounded_facts_omit_legacy_locate_entries() -> None:
    """历史定位事实可恢复但不能再作为默认模型提示的一部分。"""
    context = new_task_context("测试旧定位事实")
    context["grounded_facts"] = [
        {
            "kind": "locate",
            "label": "Safari",
            "status": "valid",
            "source_path": "/tmp/current.png",
            "conclusion": "旧事实",
            "target_id": 7,
        }
    ]
    assert grounded_facts_message(context, current_frame_path="/tmp/current.png") == "无"


async def test_side_effect_requires_task_complete_after_plain_text(settings: Settings) -> None:
    """副作用后的普通正文不能结束，必须在后置截图后显式声明完成。"""
    settings.max_iterations = 4
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "shot",
                        "type": "function",
                        "function": {"name": "screenshot", "arguments": "{}"},
                    }
                ]
            ),
            ChatDelta(
                tool_calls=[
                    {
                        "id": "move",
                        "type": "function",
                        "function": {
                            "name": "mouse_move",
                            "arguments": '{"x":8,"y":8}',
                        },
                    }
                ]
            ),
            ChatDelta(text="我认为完成了"),
            ChatDelta(
                tool_calls=[
                    {
                        "id": "done",
                        "type": "function",
                        "function": {
                            "name": "task_complete",
                            "arguments": '{"summary":"已移动","evidence":"后置截图含光标"}',
                        },
                    }
                ]
            ),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="移动鼠标")
    assert state["status"] == "done"
    assert state["task_context"]["completion_required"] is True
    assert state["task_context"]["completion_verified"] is True
    assert len(client.requests) == 4
    before_action = {item["function"]["name"] for item in client.tool_requests[1]}
    after_action = {item["function"]["name"] for item in client.tool_requests[2]}
    assert "task_complete" not in before_action
    assert "task_complete" in after_action


async def test_side_effect_expectation_verifies_required_progress(settings: Settings) -> None:
    """副作用附带 expectation 时，后置观察确认后才允许必经进度通过完成门。"""
    settings.max_iterations = 5
    client = ScriptedClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "shot",
                        "type": "function",
                        "function": {"name": "screenshot", "arguments": "{}"},
                    }
                ]
            ),
            ChatDelta(
                tool_calls=[
                    {
                        "id": "move",
                        "type": "function",
                        "function": {"name": "mouse_move", "arguments": '{"x":8,"y":8}'},
                    }
                ]
            ),
            ChatDelta(
                tool_calls=[
                    {
                        "id": "click",
                        "type": "function",
                        "function": {
                            "name": "mouse_click",
                            "arguments": (
                                '{"expectation":{"kind":"screen_changed",'
                                '"progress_id":"open-upload","target":"上传"}}'
                            ),
                        },
                    }
                ]
            ),
            ChatDelta(
                tool_calls=[
                    {
                        "id": "done",
                        "type": "function",
                        "function": {
                            "name": "task_complete",
                            "arguments": '{"summary":"已打开上传","evidence":"后置截图已获取"}',
                        },
                    }
                ]
            ),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")

    state = await runner.run(session, user_text="打开上传")

    assert state["status"] == "done"
    assert state["task_context"]["progress"] == [
        {"id": "open-upload", "label": "上传", "status": "verified", "required": True}
    ]
    click_schema = next(
        item for item in client.tool_requests[2] if item["function"]["name"] == "mouse_click"
    )
    assert "expectation" in click_schema["function"]["parameters"]["properties"]


def test_completion_evidence_accepts_separate_post_action_screenshot() -> None:
    """动作自身截图失败后，后续独立截图也可作为完成门的后置观察。"""
    context = {
        "action_history": [
            {
                "name": "mouse_move",
                "arguments": {},
                "outcome": "success",
                "has_observation": False,
                "conclusion": "动作成功但后置截图失败",
            },
            {
                "name": "screenshot",
                "arguments": {},
                "outcome": "success",
                "has_observation": True,
                "conclusion": "已补拍",
            },
        ]
    }
    assert _completion_evidence_ready(context)
    context["action_history"].pop()
    assert not _completion_evidence_ready(context)


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


async def test_expose_all_tools_is_opt_in(settings: Settings) -> None:
    """显式开关暴露完整注册表，默认运行仍使用动态工具集合。"""
    default_client = ScriptedClient([ChatDelta(text="完成")])
    default_runner, default_store = _runner(settings, default_client)
    await default_runner.run(default_store.create(model="test"), user_text="默认工具")
    default_names = {str(item["function"]["name"]) for item in default_client.tool_requests[0]}
    assert default_names < default_runner.registry.names()

    complete_client = ScriptedClient([ChatDelta(text="完成")])
    complete_runner, complete_store = _runner(settings, complete_client)
    await complete_runner.run(
        complete_store.create(model="test"),
        user_text="全部工具",
        expose_all_tools=True,
    )
    complete_names = {str(item["function"]["name"]) for item in complete_client.tool_requests[0]}
    assert complete_names == complete_runner.registry.names()


async def test_expose_all_tools_can_exclude_names(settings: Settings) -> None:
    """完整工具模式可同时从 schema 和 Act 允许集合排除指定名称。"""
    client = ScriptedClient([ChatDelta(text="完成")])
    runner, store = _runner(settings, client)
    excluded = {"activate_app", "click"}

    state = await runner.run(
        store.create(model="test"),
        user_text="排除部分工具",
        expose_all_tools=True,
        excluded_tools=excluded,
    )

    schema_names = {str(item["function"]["name"]) for item in client.tool_requests[0]}
    assert schema_names == runner.registry.names() - excluded
    assert not excluded & set(state["allowed_tools"])


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


async def test_next_turn_invalidates_saved_view_frame(settings: Settings) -> None:
    """新桌面任务刷新上回合截图坐标，不复用旧帧。"""
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
            ChatDelta(text="需要先截图"),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    first = await runner.run(session, user_text="截图")
    assert first["status"] == "done"
    session = store.get(session.id)
    assert session is not None
    assert session.view_frame is not None
    first_frame_path = session.view_frame["image_path"]
    clear_desktop_context()
    second = await runner.run(session, user_text="移动")
    assert second["status"] == "done"
    initial_tools = {item["function"]["name"] for item in client.tool_requests[-1]}
    assert "mouse_move" in initial_tools
    assert session.view_frame is not None
    assert session.view_frame["image_path"] != first_frame_path
    assert session.locate_hits == {}


def test_os_contract_darwin_not_windows() -> None:
    """darwin 文案含 macOS 且否定 Windows。"""
    text = os_contract("Darwin")
    assert "macOS" in text
    assert "不是 Windows" in text
    assert "command" in text
    assert "不是 Windows" not in os_contract("Windows")


def test_system_prompt_separates_user_reply_from_native_tools() -> None:
    """提示词要求单步原生调用，且不要求正文 JSON 协议。"""
    assert "选择恰好一个下一步动作" in GUI_SYSTEM_PROMPT
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
    assert "locate" not in content
    assert "target_id" not in content
    assert "ocr_locate" not in content
    assert "当前截图视图是" in content
    assert "element_id" in content
    assert "红十字" in content
    assert "后置观察" in content
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
                        "id": "shot",
                        "type": "function",
                        "function": {"name": "screenshot", "arguments": "{}"},
                    }
                ]
            ),
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
            ChatDelta(
                tool_calls=[
                    {
                        "id": "done",
                        "type": "function",
                        "function": {
                            "name": "task_complete",
                            "arguments": '{"summary":"移完了","evidence":"截图含光标"}',
                        },
                    }
                ]
            ),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="点一下")
    tool_msgs = [msg for msg in state["messages"] if msg.get("role") == "tool"]
    move_message = next(item for item in tool_msgs if item.get("name") == "mouse_move")
    assert isinstance(move_message["content"], dict)
    assert move_message["content"]["images"]
    tool_encoded = next(
        item
        for item in client.requests[2]
        if item.get("role") == "tool" and item.get("tool_call_id") == "clk"
    )
    types = [part["type"] for part in tool_encoded["content"]]
    assert "text" in types and "image_url" in types


class FailingStreamClient:
    """`stream` 抛出推理 HTTP 错误，供测试落盘。"""

    async def stream(
        self,
        messages,
        *,
        tools=None,
        on_token=None,
        on_reasoning=None,
        should_stop=None,
        on_retry=None,
    ):
        """始终失败。"""
        raise RuntimeError("推理服务返回 400：maximum context length")


class RetryReportingClient:
    """先报告安全重试通知，再返回指定结果的假客户端。"""

    def __init__(self, deltas: list[ChatDelta]) -> None:
        """参数：`deltas` 为每次逻辑模型调用的最终结果。"""
        self.deltas = list(deltas)
        self.calls = 0

    async def stream(
        self,
        messages,
        *,
        tools=None,
        on_token=None,
        on_reasoning=None,
        should_stop=None,
        on_retry=None,
    ):
        """每次逻辑调用只报告一次传输重试，不重复返回中间消息。"""
        self.calls += 1
        if on_retry:
            on_retry(
                RetryNotice(
                    attempt=2,
                    max_attempts=6,
                    reason_code="transport_connecterror",
                    status_code=None,
                    delay_ms=500,
                    error="Authorization: Bearer secret-token",
                )
            )
        delta = self.deltas.pop(0)
        if delta.reasoning and on_reasoning:
            on_reasoning(delta.reasoning)
        if delta.text and on_token:
            on_token(delta.text)
        return delta


class RetriedFailureClient:
    """模拟两次网络尝试后仍失败的客户端。"""

    async def stream(
        self,
        messages,
        *,
        tools=None,
        on_token=None,
        on_reasoning=None,
        should_stop=None,
        on_retry=None,
    ):
        """先报告一次重试，再抛出带尝试统计的最终错误。"""
        if on_retry:
            on_retry(
                RetryNotice(
                    attempt=2,
                    max_attempts=2,
                    reason_code="http_503",
                    status_code=503,
                    delay_ms=500,
                    error="service unavailable",
                )
            )
        raise InferenceRequestError(
            "推理服务返回 503：service unavailable（已重试 1 次，共尝试 2 次。）",
            metadata=RetryMetadata(
                attempt_count=2,
                retry_count=1,
                reason_code="http_503",
                status_code=503,
            ),
        )


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
        if calls == 3:
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
            assert calls == 2
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


async def test_coordinate_move_then_require_click_verification(
    settings: Settings,
) -> None:
    """禁用定位器后仍可用截图视图像素移动，并进入无坐标点击核验链路。"""
    calls = [
        ("shot", "screenshot", {}),
        ("move", "mouse_move", {"x": 10, "y": 10}),
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
        + [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "done",
                        "type": "function",
                        "function": {
                            "name": "task_complete",
                            "arguments": '{"summary":"完成","evidence":"光标截图已核验"}',
                        },
                    }
                ]
            )
        ]
    )
    settings.max_iterations = 4
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="打开 Safari")
    assert state["status"] == "done"
    move_request = client.requests[1]
    move_user = next(item for item in move_request if item.get("role") == "user")
    assert "Safari" in str(move_user["content"])
    assert "target_id" not in str(move_user["content"])
    click_request = client.requests[2]
    click_user = next(item for item in click_request if item.get("role") == "user")
    assert "Safari" in str(click_user["content"])
    assert "task_complete" in str(click_user["content"])
    loaded = store.get(session.id)
    assert loaded is not None and loaded.task_context is not None
    assert loaded.task_context["grounded_facts"] == []


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


async def test_model_retry_event_keeps_one_logical_call_and_one_message(
    settings: Settings,
) -> None:
    """重试事件位于同一模型调用内，脱敏且只提交成功助手消息。"""
    client = RetryReportingClient([ChatDelta(text="完成", attempt_count=2, retry_count=1)])
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="重试")
    events = _run_events(settings, state["run_id"])
    types = [item["event_type"] for item in events]
    assert types.count("model.started") == 1
    assert types.count("model.retrying") == 1
    assert types.count("model.completed") == 1
    retrying = next(item for item in events if item["event_type"] == "model.retrying")
    completed = next(item for item in events if item["event_type"] == "model.completed")
    terminal = next(item for item in events if item["event_type"] == "run.completed")
    assert retrying["data"]["attempt"] == 2
    assert retrying["data"]["delay_ms"] == 500
    assert "secret-token" not in json.dumps(retrying, ensure_ascii=False)
    assert completed["data"]["attempt_count"] == 2
    assert completed["data"]["retry_count"] == 1
    assert terminal["data"]["model_calls"] == 1
    loaded = store.get(session.id)
    assert loaded is not None
    assert [message.role for message in loaded.messages].count("assistant") == 1


async def test_retry_after_tool_does_not_replay_tool(settings: Settings) -> None:
    """下一轮模型重试不会重新执行上一轮已成功的截图工具。"""
    client = RetryReportingClient(
        [
            ChatDelta(
                tool_calls=[
                    {
                        "id": "shot",
                        "type": "function",
                        "function": {"name": "screenshot", "arguments": "{}"},
                    }
                ],
                attempt_count=2,
                retry_count=1,
            ),
            ChatDelta(text="已观察", attempt_count=2, retry_count=1),
        ]
    )
    runner, store = _runner(settings, client)
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="截图")
    events = _run_events(settings, state["run_id"])
    tool_starts = [item for item in events if item["event_type"] == "tool.started"]
    tool_messages = [item for item in state["messages"] if item.get("role") == "tool"]
    assert len(tool_starts) == 1
    assert len(tool_messages) == 1
    assert client.calls == 2


async def test_retry_exhaustion_persists_once_with_attempt_metadata(settings: Settings) -> None:
    """重试耗尽只形成一次最终错误和检查点，不追加失败尝试消息。"""
    runner, store = _runner(settings, RetriedFailureClient())
    session = store.create(model="qwen3.5-2b")
    state = await runner.run(session, user_text="失败")
    events = _run_events(settings, state["run_id"])
    retrying = [item for item in events if item["event_type"] == "model.retrying"]
    failures = [item for item in events if item["event_type"] == "model.failed"]
    assert len(retrying) == 1
    assert len(failures) == 1
    assert failures[0]["data"]["attempt_count"] == 2
    assert failures[0]["data"]["retry_count"] == 1
    loaded = store.get(session.id)
    assert loaded is not None
    assert loaded.status == "error"
    assert "已重试 1 次" in str(loaded.checkpoint.get("error"))
    assert [message.role for message in loaded.messages] == ["user"]
