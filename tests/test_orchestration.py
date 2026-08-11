"""覆盖受控 text-or-tool 循环、工具门、Guard、恢复和终止条件。"""

from __future__ import annotations

import tempfile
import time
import unittest
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

from max_agent.orchestration.models import (
    AgentMessage,
    AgentRequest,
    BudgetLimits,
    FinalTextResponse,
    ModelTurnResponse,
    TaskStatus,
    ToolUseResponse,
)
from max_agent.orchestration.resources import ResourceRef
from max_agent.runtime import build_agent_runtime
from max_agent.tools.base import ToolContext, ToolPermission, ToolPhase, ToolReceipt
from max_agent.tools.registry import ToolRegistry

WINDOW = {
    "hwnd": 7,
    "process_id": 42,
    "executable_path": "C:/Windows/System32/notepad.exe",
    "title": "未命名 - 记事本",
}
WINDOW_ITEM = {
    **WINDOW,
    "bounds": {"left": 100, "top": 100, "width": 800, "height": 600},
    "foreground": True,
    "taskbar_visible": True,
}


class _EmptyInput(BaseModel):
    pass


class _ScreenInput(BaseModel):
    monitor_index: int = Field(default=0, ge=0)


class _OcrInput(BaseModel):
    image_ref: ResourceRef
    region: dict[str, int] | None = None


class _Scene:
    """内存中的受控记事本夹具，不接触真实窗口或用户文件。"""

    def __init__(self) -> None:
        self.text = "原有内容"
        self.revision = 0
        self.foreground = dict(WINDOW)
        self.edit_focused = True
        self.unsaved = False
        self.observe_windows_calls = 0
        self.observe_screen_calls = 0
        self.ocr_calls = 0


class _ObserveWindows:
    name = "observe_windows"
    description = "List visible windows."
    permission = ToolPermission.OBSERVE
    allowed_phases = frozenset({ToolPhase.TOOL, ToolPhase.OBSERVE_AFTER_ACTION})
    timeout_seconds = 5.0
    recoverable = True
    model_visible = True
    side_effect = False
    input_model = _EmptyInput

    def __init__(self, scene: _Scene) -> None:
        self.scene = scene

    def invoke(
        self, tool_input: _EmptyInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        self.scene.observe_windows_calls += 1
        return ToolReceipt(
            tool_name=self.name, success=True, data={"windows": [WINDOW_ITEM]}
        )


class _ObserveScreen:
    name = "observe_screen"
    description = "Capture a task-scoped image."
    permission = ToolPermission.OBSERVE
    allowed_phases = frozenset({ToolPhase.TOOL, ToolPhase.OBSERVE_AFTER_ACTION})
    timeout_seconds = 5.0
    recoverable = True
    model_visible = True
    side_effect = False
    input_model = _ScreenInput

    def __init__(self, scene: _Scene) -> None:
        self.scene = scene

    def invoke(
        self, tool_input: _ScreenInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        self.scene.observe_screen_calls += 1
        image = Image.new("RGB", (1000, 800), color=(self.scene.revision % 255, 0, 0))
        assert context is not None
        image_ref = context.resources.put(context.task_id, "image", image)
        return ToolReceipt(
            tool_name=self.name,
            success=True,
            data={
                "image_ref": image_ref.model_dump(),
                "captured_at": time.time(),
                "bounds": {"left": 0, "top": 0, "width": 1000, "height": 800},
                "dpi": 96,
                "foreground_window": self.scene.foreground,
            },
        )


class _RecognizeText:
    name = "recognize_text"
    description = "Recognize text from one task image."
    permission = ToolPermission.OBSERVE
    allowed_phases = frozenset({ToolPhase.TOOL, ToolPhase.OBSERVE_AFTER_ACTION})
    timeout_seconds = 5.0
    recoverable = True
    model_visible = True
    side_effect = False
    input_model = _OcrInput

    def __init__(self, scene: _Scene) -> None:
        self.scene = scene

    def invoke(
        self, tool_input: _OcrInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        assert context is not None
        context.resources.get(tool_input.image_ref, context.task_id, "image")
        self.scene.ocr_calls += 1
        return ToolReceipt(
            tool_name=self.name,
            success=True,
            data={
                "lines": [
                    {
                        "text": self.scene.text,
                        "confidence": 0.99,
                        "bounds": {"left": 120, "top": 150, "width": 400, "height": 40},
                    }
                ]
            },
        )


Step = ModelTurnResponse | Callable[[Sequence[AgentMessage]], ModelTurnResponse]


class _ModelSession:
    def __init__(self, steps: list[Step]) -> None:
        self.steps = steps
        self.calls: list[
            tuple[list[AgentMessage], Sequence[dict[str, object]], str, int]
        ] = []
        self.reset_calls = 0

    def respond(
        self,
        messages: Sequence[AgentMessage],
        tools: Sequence[dict[str, object]],
        *,
        reasoning_mode: str = "fast",
        images: Sequence[object] = (),
        consume_correction: Callable[[], bool] | None = None,
    ) -> ModelTurnResponse:
        copied = list(messages)
        self.calls.append((copied, tools, reasoning_mode, len(images)))
        if not self.steps:
            raise AssertionError("fake model response queue is empty")
        step = self.steps.pop(0)
        return step(copied) if callable(step) else step

    def reset(self) -> None:
        self.reset_calls += 1


class _DesktopAdapter:
    def __init__(self, scene: _Scene) -> None:
        self.scene = scene
        self.actions = []
        self.release_calls = 0
        self.apply_effect = True

    def execute(self, action) -> None:
        self.actions.append(action)
        if not self.apply_effect:
            return
        if action.kind == "activate_window":
            self.scene.foreground = (
                action.window.model_dump() if action.window else None
            )
        elif action.kind == "key_chord" and action.keys == ["ctrl", "end"]:
            self.scene.edit_focused = True
        elif action.kind == "type_text" and self.scene.edit_focused:
            self.scene.text += action.text or ""
            self.scene.unsaved = True
        self.scene.revision += 1

    def foreground_identity(self) -> dict[str, object] | None:
        return self.scene.foreground

    def release_all(self) -> None:
        self.release_calls += 1


def _tool(name: str, arguments: dict[str, Any] | None = None) -> ToolUseResponse:
    return ToolUseResponse(tool_name=name, arguments=arguments or {})


def _ocr_from_last_screen(messages: Sequence[AgentMessage]) -> ToolUseResponse:
    last = messages[-1]
    assert isinstance(last.content, dict)
    return _tool("recognize_text", {"image_ref": last.content["data"]["image_ref"]})


def _registry(scene: _Scene) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in (_ObserveWindows(scene), _ObserveScreen(scene), _RecognizeText(scene)):
        registry.register(tool)
    return registry


class OrchestrationTests(unittest.TestCase):
    def _runtime(self, steps: list[Step]):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        scene = _Scene()
        model = _ModelSession(steps)
        adapter = _DesktopAdapter(scene)
        runtime = build_agent_runtime(
            Path(temporary.name),
            Path(temporary.name) / "artifacts",
            lambda: "fake",
            model_session=model,
            desktop_adapter=adapter,
            registry=_registry(scene),
        )
        return runtime, scene, model, adapter

    def test_default_runtime_registers_every_perception_and_internal_capability(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            scene = _Scene()
            runtime = build_agent_runtime(
                Path(temporary),
                Path(temporary) / "artifacts",
                lambda: "fake",
                model_session=_ModelSession([FinalTextResponse(text="完成")]),
                desktop_adapter=_DesktopAdapter(scene),
            )
        self.assertEqual(
            set(runtime.registry.names),
            {
                "observe_screen",
                "observe_windows",
                "recognize_text",
                "observe_ui_elements",
                "preprocess_image",
                "match_template",
                "annotate_som",
                "invoke_model",
                "request_user",
                "desktop_action",
                "approve_action",
                "execute_action",
                "verify_result",
                "recover",
                "archive_run",
            },
        )

    def test_first_turn_text_does_not_observe_or_acquire_desktop_lock(self) -> None:
        runtime, scene, model, adapter = self._runtime(
            [FinalTextResponse(text="直接回答")]
        )
        events = []
        result = runtime.run(AgentRequest(user_goal="普通知识问题"), events.append)

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(result.response_text, "直接回答")
        self.assertEqual(
            (scene.observe_windows_calls, scene.observe_screen_calls, scene.ocr_calls),
            (0, 0, 0),
        )
        self.assertEqual(adapter.actions, [])
        self.assertEqual(adapter.release_calls, 0)
        self.assertIsNone(runtime.session_lock.owner)
        self.assertEqual(model.calls[0][3], 0)
        self.assertTrue(events)
        exposed = {item["name"] for item in model.calls[0][1]}
        self.assertIn("desktop_action", exposed)
        self.assertNotIn("approve_action", exposed)
        self.assertNotIn("execute_action", exposed)
        self.assertNotIn("archive_run", exposed)

    def test_read_only_tools_loop_in_one_request_and_images_stay_task_scoped(
        self,
    ) -> None:
        runtime, scene, model, adapter = self._runtime(
            [
                _tool("observe_windows"),
                _tool("observe_screen"),
                _ocr_from_last_screen,
                FinalTextResponse(text="记事本内容是：原有内容"),
            ]
        )
        result = runtime.run(AgentRequest(user_goal="查看记事本内容"))

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(
            (scene.observe_windows_calls, scene.observe_screen_calls, scene.ocr_calls),
            (1, 1, 1),
        )
        self.assertEqual(adapter.actions, [])
        self.assertEqual(adapter.release_calls, 0)
        self.assertEqual(len(model.calls), 4)
        self.assertEqual(runtime.resources.count(), 0)

    def test_desktop_action_must_pass_guard_reobserve_and_ocr_verification(
        self,
    ) -> None:
        action = {"kind": "type_text", "window": WINDOW, "text": "\n新增内容"}
        runtime, scene, model, adapter = self._runtime(
            [
                _tool("observe_windows"),
                _tool("observe_screen"),
                _ocr_from_last_screen,
                _tool("desktop_action", action),
                FinalTextResponse(text="已追加并通过 OCR 验证"),
            ]
        )
        result = runtime.run(AgentRequest(user_goal="在记事本末尾追加新增内容"))

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(len(adapter.actions), 1)
        self.assertIn("新增内容", scene.text)
        self.assertEqual(scene.observe_screen_calls, 2)
        self.assertEqual(scene.ocr_calls, 2)
        self.assertTrue(
            any(
                item.startswith("ocr_contains_input_sha256:")
                for item in result.verification_evidence
            )
        )
        self.assertNotIn("新增内容", str(result.history))

    def test_notepad_vertical_flow_activates_focuses_appends_unicode_and_verifies(
        self,
    ) -> None:
        activate = {"kind": "activate_window", "window": WINDOW}
        focus = {"kind": "click", "window": WINDOW, "x": 500, "y": 400}
        focus_end = {"kind": "key_chord", "window": WINDOW, "keys": ["ctrl", "end"]}
        append = {"kind": "type_text", "window": WINDOW, "text": "\nMAX-验收-Ω-终点"}
        runtime, scene, _, adapter = self._runtime(
            [
                _tool("observe_windows"),
                _tool("observe_screen"),
                _ocr_from_last_screen,
                _tool("desktop_action", activate),
                _tool("desktop_action", focus),
                _tool("desktop_action", focus_end),
                _tool("desktop_action", append),
                FinalTextResponse(text="记事本追加内容已由新 OCR 证据确认"),
            ]
        )
        result = runtime.run(
            AgentRequest(user_goal="查看记事本并在末尾追加唯一 Unicode 标记")
        )

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(
            [action.kind for action in adapter.actions],
            ["activate_window", "click", "key_chord", "type_text"],
        )
        self.assertTrue(scene.edit_focused)
        self.assertTrue(scene.unsaved)
        self.assertTrue(scene.text.endswith("MAX-验收-Ω-终点"))
        self.assertEqual(scene.observe_screen_calls, 5)
        self.assertTrue(
            any(
                item.startswith("ocr_contains_input_sha256:")
                for item in result.verification_evidence
            )
        )

    def test_internal_tool_selected_by_model_is_rejected_without_execution(
        self,
    ) -> None:
        runtime, scene, _, adapter = self._runtime(
            [_tool("approve_action"), FinalTextResponse(text="内部工具不可调用")]
        )
        result = runtime.run(AgentRequest(user_goal="绕过 Guard"))

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(adapter.actions, [])
        self.assertEqual(scene.observe_screen_calls, 0)
        self.assertTrue(
            any(item.error_code == "permission_denied" for item in result.receipts)
        )

    def test_invalid_tool_arguments_are_returned_to_model_without_execution(
        self,
    ) -> None:
        runtime, _, model, adapter = self._runtime(
            [
                _tool("observe_screen", {"monitor_index": -1}),
                FinalTextResponse(text="参数被工具门拒绝"),
            ]
        )
        result = runtime.run(AgentRequest(user_goal="非法参数"))

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(adapter.actions, [])
        self.assertTrue(
            any(item.error_code == "invalid_input" for item in result.receipts)
        )
        self.assertEqual(model.calls[-1][0][-1].role, "tool")

    def test_repeated_equivalent_tool_calls_wait_for_user(self) -> None:
        runtime, _, _, adapter = self._runtime(
            [_tool("observe_windows") for _ in range(4)]
        )
        result = runtime.run(
            AgentRequest(
                user_goal="循环", budgets=BudgetLimits(repeated_calls=2, model_turns=8)
            )
        )

        self.assertEqual(result.status, TaskStatus.WAITING_USER)
        self.assertEqual(result.reason, "NO_PROGRESS")
        self.assertEqual(adapter.actions, [])
        self.assertIsNone(runtime.session_lock.owner)

    def test_model_budget_exhaustion_fails_closed(self) -> None:
        runtime, _, _, adapter = self._runtime([_tool("observe_windows")])
        result = runtime.run(
            AgentRequest(user_goal="预算测试", budgets=BudgetLimits(model_turns=1))
        )

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertIn("budget", (result.reason or "").lower())
        self.assertEqual(adapter.actions, [])

    def test_unverified_final_text_is_rejected_and_runtime_requests_help(self) -> None:
        action = {"kind": "type_text", "window": WINDOW, "text": "不会出现"}
        runtime, _, _, adapter = self._runtime(
            [
                _tool("observe_windows"),
                _tool("observe_screen"),
                _ocr_from_last_screen,
                _tool("desktop_action", action),
                FinalTextResponse(text="未经验证的成功声明"),
                _tool("request_user", {"question": "请检查记事本焦点"}),
            ]
        )
        adapter.apply_effect = False
        result = runtime.run(AgentRequest(user_goal="追加内容"))

        self.assertEqual(result.status, TaskStatus.WAITING_USER)
        self.assertNotEqual(result.response_text, "未经验证的成功声明")
        self.assertTrue(
            any(item.tool_name == "goal_verification" for item in result.receipts)
        )

    def test_busy_desktop_session_fails_before_execution(self) -> None:
        action = {"kind": "type_text", "window": WINDOW, "text": "不会执行"}
        runtime, _, _, adapter = self._runtime(
            [
                _tool("observe_windows"),
                _tool("observe_screen"),
                _ocr_from_last_screen,
                _tool("desktop_action", action),
            ]
        )
        runtime.session_lock.acquire("another-task")
        self.addCleanup(runtime.session_lock.release, "another-task")
        result = runtime.run(AgentRequest(user_goal="桌面忙碌"))

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.reason, "SESSION_BUSY")
        self.assertEqual(adapter.actions, [])

    def test_cancelled_request_never_calls_model_or_desktop(self) -> None:
        runtime, scene, model, adapter = self._runtime(
            [FinalTextResponse(text="不应调用")]
        )
        result = runtime.run(AgentRequest(user_goal="取消", cancelled=True))

        self.assertEqual(result.status, TaskStatus.ABORTED)
        self.assertEqual(model.calls, [])
        self.assertEqual(scene.observe_screen_calls, 0)
        self.assertEqual(adapter.actions, [])

    def test_wait_user_releases_resources_and_next_message_resumes_same_task(
        self,
    ) -> None:
        runtime, _, model, adapter = self._runtime(
            [
                _tool("request_user", {"question": "请先登录"}),
                FinalTextResponse(text="继续完成"),
            ]
        )
        first = runtime.run(
            AgentRequest(user_goal="需要登录的任务", task_id="stable-task")
        )
        self.assertEqual(first.status, TaskStatus.WAITING_USER)
        self.assertEqual(first.resume_token, "stable-task")
        self.assertEqual(runtime.resources.count(), 0)
        self.assertIsNone(runtime.session_lock.owner)

        second = runtime.run(AgentRequest(user_goal="已登录"))
        self.assertEqual(second.task_id, "stable-task")
        self.assertEqual(second.status, TaskStatus.SUCCEEDED)
        self.assertEqual(model.calls[-1][0][-1].content, "已登录")
        self.assertEqual(adapter.release_calls, 0)

    def test_waiting_state_drops_original_sensitive_goal_and_question_arguments(
        self,
    ) -> None:
        secret = "PASSWORD-SENTINEL-8821"
        runtime, _, _, _ = self._runtime(
            [_tool("request_user", {"question": f"请输入验证码 {secret}"})]
        )
        result = runtime.run(AgentRequest(user_goal=f"使用密码 {secret} 登录"))

        self.assertEqual(result.status, TaskStatus.WAITING_USER)
        self.assertIsNotNone(runtime._suspended)
        self.assertNotIn(secret, str(runtime._suspended.model_dump()))
        self.assertEqual(runtime._suspended.question, "需要用户继续处理。")

    def test_high_impact_confirmation_invalidates_old_state_and_reguards_action(
        self,
    ) -> None:
        save = {"kind": "key_chord", "window": WINDOW, "keys": ["ctrl", "s"]}
        runtime, scene, _, adapter = self._runtime(
            [
                _tool("observe_windows"),
                _tool("observe_screen"),
                _ocr_from_last_screen,
                _tool("desktop_action", save),
                _tool("observe_windows"),
                _tool("observe_screen"),
                _ocr_from_last_screen,
                _tool("desktop_action", save),
                FinalTextResponse(text="已在重新观察和确认后执行"),
            ]
        )
        first = runtime.run(AgentRequest(user_goal="保存记事本"))
        self.assertEqual(first.status, TaskStatus.WAITING_USER)
        self.assertEqual(adapter.actions, [])
        self.assertEqual(runtime.resources.count(), 0)

        second = runtime.run(AgentRequest(user_goal="确认允许"))
        self.assertEqual(second.status, TaskStatus.SUCCEEDED)
        self.assertEqual(len(adapter.actions), 1)
        self.assertEqual(scene.observe_screen_calls, 3)

    def test_event_callback_changes_no_result_and_contains_only_audit_fields(
        self,
    ) -> None:
        with_events, _, _, _ = self._runtime([FinalTextResponse(text="一致")])
        events = []
        first = with_events.run(
            AgentRequest(user_goal="事件", task_id="same"), events.append
        )
        without_events, _, _, _ = self._runtime([FinalTextResponse(text="一致")])
        second = without_events.run(AgentRequest(user_goal="事件", task_id="same"))

        self.assertEqual(
            first.model_dump(exclude={"cleanup_errors"}),
            second.model_dump(exclude={"cleanup_errors"}),
        )
        self.assertTrue(events)
        for event in events:
            self.assertEqual(
                set(event.model_dump()),
                {"phase", "state", "tool_name", "elapsed_seconds", "message"},
            )


if __name__ == "__main__":
    unittest.main()
