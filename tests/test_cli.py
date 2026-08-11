"""验证 CLI 路由、参数边界及 doctor 归档行为。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from max_agent.cli import _doctor_operation, _interactive_dispatch, main
from max_agent.console_core import ConsoleEventKind
from max_agent.diagnostics import DiagnosticResult
from max_agent.orchestration.models import AgentResult, RuntimeEvent, TaskStatus


def _agent_result(text: str, status: TaskStatus = TaskStatus.SUCCEEDED) -> AgentResult:
    return AgentResult(task_id="task", status=status, response_text=text)


class CliTests(unittest.TestCase):
    def test_default_and_chat_start_the_same_textual_interface(self) -> None:
        with patch("max_agent.cli.run_textual_chat") as start_chat:
            main([])
            main(["--chat"])

        self.assertEqual(start_chat.call_count, 2)

    def test_unsupported_cli_operations_are_rejected(self) -> None:
        for operation in ("download-model", "--doctor", "--fallback", "--textual"):
            with self.subTest(operation=operation), self.assertRaises(SystemExit):
                main([operation])

    def test_help_lists_available_operations(self) -> None:
        with self.assertRaises(SystemExit):
            main(["--help"])

    def test_doctor_cli_accepts_artifact_root_and_explicit_desktop_probe(self) -> None:
        with patch("max_agent.cli._doctor", return_value=0) as doctor:
            self.assertEqual(main(["doctor", "--artifact-root", "evidence"]), 0)
            self.assertEqual(
                main(["doctor", "--artifact-root", "evidence", "--desktop-probe"]),
                0,
            )

        self.assertEqual(
            doctor.call_args_list[0].args,
            (Path("evidence"),),
        )
        self.assertEqual(doctor.call_args_list[0].kwargs, {"desktop_probe": False})
        self.assertEqual(doctor.call_args_list[1].kwargs, {"desktop_probe": True})

    def test_doctor_cli_rejects_unknown_arguments(self) -> None:
        with self.assertRaises(SystemExit):
            main(["doctor", "--unknown"])

    def test_doctor_command_archives_its_result(self) -> None:
        result = DiagnosticResult(
            python_version="3.12",
            packages={},
            cuda_available=True,
            cuda_version="12.8",
            bf16_supported=True,
            failures=[],
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("max_agent.cli.run_diagnostics", return_value=result),
        ):
            operation = _doctor_operation(Path(directory))
            run_directory = next(Path(directory).iterdir())
            self.assertEqual(operation.kind, "doctor")
            self.assertEqual(operation.exit_code, 0)
            self.assertTrue((run_directory / "config.yaml").exists())
            self.assertTrue((run_directory / "environment.json").exists())
            self.assertTrue((run_directory / "result.json").exists())

    def test_interactive_model_command_does_not_call_chat(self) -> None:
        with (
            patch("max_agent.cli.LocalChatRuntime") as runtime_type,
            patch("max_agent.cli.run_textual_chat") as start_chat,
            patch("max_agent.cli.build_agent_runtime") as build_runtime,
        ):
            runtime = runtime_type.return_value
            runtime.available_models.return_value = ("Qwen/Qwen3.5-2B",)
            runtime.selected_model = "Qwen/Qwen3.5-2B"
            runtime.state = "unloaded"
            main([])
            dispatch = start_chat.call_args.args[0]
            result = dispatch("/model")

        self.assertEqual(result.kind, "model")
        self.assertIn(
            "Qwen/Qwen3.5-2B", "\n".join(event.text for event in result.events)
        )
        runtime.reply.assert_not_called()
        build_runtime.return_value.run.assert_not_called()

    def test_chat_creates_exactly_one_agent_runtime_request(self) -> None:
        runtime = Mock()
        runtime.selected_model = "fake"
        runtime.state = "ready"
        agent = Mock()
        agent.suspended_task_id = None
        agent.run.return_value = _agent_result("普通回复")
        dispatch, _ = _interactive_dispatch(Path("artifacts"), runtime, agent)
        emitted = []

        result = dispatch("你好", emitted.append)

        self.assertEqual(result.events[-1].text, "普通回复")
        self.assertFalse(any(event.kind == ConsoleEventKind.TOOL for event in emitted))
        agent.run.assert_called_once()
        self.assertEqual(agent.run.call_args.args[0].user_goal, "你好")
        runtime.reply.assert_not_called()

    def test_runtime_events_map_to_existing_notice_and_tool_events(self) -> None:
        runtime = Mock()
        runtime.selected_model = "fake"
        runtime.state = "ready"
        agent = Mock()
        agent.suspended_task_id = None

        def run(_request, emit):
            emit(
                RuntimeEvent(phase="reason", state="running", tool_name="invoke_model")
            )
            emit(
                RuntimeEvent(
                    phase="reason",
                    state="succeeded",
                    tool_name="invoke_model",
                    elapsed_seconds=0.1,
                )
            )
            emit(
                RuntimeEvent(phase="tool", state="running", tool_name="observe_windows")
            )
            emit(
                RuntimeEvent(
                    phase="tool",
                    state="succeeded",
                    tool_name="observe_windows",
                    elapsed_seconds=0.2,
                )
            )
            return _agent_result("完成")

        agent.run.side_effect = run
        emitted = []
        dispatch, _ = _interactive_dispatch(Path("artifacts"), runtime, agent)
        result = dispatch("查看窗口", emitted.append)

        self.assertEqual(result.kind, "chat")
        self.assertEqual(
            [event.kind for event in emitted],
            [
                ConsoleEventKind.NOTICE,
                ConsoleEventKind.NOTICE,
                ConsoleEventKind.TOOL,
                ConsoleEventKind.TOOL,
            ],
        )
        self.assertEqual({event.text for event in emitted[-2:]}, {"observe_windows"})

    def test_waiting_result_status_and_next_input_share_same_adapter(self) -> None:
        runtime = Mock()
        runtime.selected_model = "fake"
        runtime.state = "ready"
        agent = Mock()
        agent.suspended_task_id = "task"
        agent.run.side_effect = [
            _agent_result("请先登录", TaskStatus.WAITING_USER),
            _agent_result("已继续"),
        ]
        dispatch, status = _interactive_dispatch(Path("artifacts"), runtime, agent)

        first = dispatch("登录后继续")
        second = dispatch("已登录")

        self.assertEqual(first.events[-1].text, "请先登录")
        self.assertEqual(second.events[-1].text, "已继续")
        self.assertEqual(agent.run.call_count, 2)
        self.assertEqual(status().runtime_state, "waiting_user")

    def test_model_clear_quit_and_status_coordinate_agent_lifecycle(self) -> None:
        runtime = Mock()
        runtime.selected_model = "old"
        runtime.state = "ready"
        runtime.available_models.return_value = ("old", "new")

        def select(name):
            runtime.selected_model = name

        runtime.select_model.side_effect = select
        agent = Mock()
        agent.suspended_task_id = None
        dispatch, status = _interactive_dispatch(Path("artifacts"), runtime, agent)

        self.assertEqual(dispatch("/model new").kind, "model")
        self.assertEqual(dispatch("/clear").kind, "clear")
        self.assertTrue(dispatch("/quit").should_exit)
        self.assertEqual(agent.clear.call_count, 3)
        self.assertEqual(runtime.clear_history.call_count, 2)
        self.assertEqual(
            status().safety_boundary, "本地 · Agent Guard · 受控桌面 · 无网络"
        )
