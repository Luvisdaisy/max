"""验证 CLI 路由、参数边界及 doctor 归档行为。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from max_agent.cli import _doctor_operation, _interactive_dispatch, main
from max_agent.diagnostics import DiagnosticResult
from max_agent.tools.perception.screen import ObserveScreenTool
from max_agent.tools.registry import ToolRegistry


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
        ):
            runtime = runtime_type.return_value
            runtime.available_models.return_value = ("Qwen/Qwen3.5-2B",)
            runtime.selected_model = "Qwen/Qwen3.5-2B"
            main([])
            dispatch = start_chat.call_args.args[0]
            result = dispatch("/model")

        self.assertEqual(result.kind, "model")
        self.assertIn("Qwen/Qwen3.5-2B", "\n".join(result.messages))
        runtime.reply.assert_not_called()

    def test_chat_allows_model_to_decline_tools(self) -> None:
        runtime = Mock()
        runtime.reply.side_effect = ['{"tool_name": null}', "普通回复"]
        dispatch = _interactive_dispatch(Path("artifacts"), runtime)

        result = dispatch("你好")

        self.assertEqual(result.messages[-1], "普通回复")
        self.assertEqual(runtime.reply.call_count, 2)

    def test_chat_returns_visual_explanation_after_screen_tool_call(self) -> None:
        registry = ToolRegistry()
        registry.register(
            ObserveScreenTool(
                capture=lambda _: {
                    "image": Image.new("RGB", (1, 1)),
                    "width": 1,
                    "height": 1,
                    "bounds": {},
                    "dpi": None,
                }
            )
        )
        runtime = Mock()
        runtime.reply.return_value = '{"tool_name": "observe_screen"}'
        runtime.explain_image.return_value = "这是当前桌面的解释。"
        with patch("max_agent.cli.build_default_registry", return_value=registry):
            result = _interactive_dispatch(Path("artifacts"), runtime)("描述当前桌面")

        self.assertEqual(result.messages[-1], "这是当前桌面的解释。")
        runtime.explain_image.assert_called_once()
