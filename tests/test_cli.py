import unittest
import sys
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from max_agent.cli import app


class CliTests(unittest.TestCase):
    def test_doctor_flag_dispatches_non_interactive_operation(self) -> None:
        with patch("max_agent.cli._doctor", return_value=0) as doctor:
            result = CliRunner().invoke(app, ["--doctor"])

        self.assertEqual(result.exit_code, 0)
        doctor.assert_called_once()

    def test_doctor_command_dispatches_non_interactive_operation(self) -> None:
        with patch("max_agent.cli._doctor", return_value=0) as doctor:
            result = CliRunner().invoke(app, ["doctor"])

        self.assertEqual(result.exit_code, 0)
        doctor.assert_called_once()

    def test_doctor_renders_readable_summary(self) -> None:
        with patch("max_agent.cli.run_diagnostics") as diagnostics:
            diagnostics.return_value = type("Result", (), {"ok": True, "to_dict": lambda self: {}, "checks": [], "failures": []})()
            result = CliRunner().invoke(app, ["doctor"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Doctor 结果", result.output)

    def test_desktop_probe_is_explicit(self) -> None:
        with patch("max_agent.cli._doctor", return_value=0) as doctor:
            result = CliRunner().invoke(app, ["doctor", "--desktop-probe"])

        self.assertEqual(result.exit_code, 0)
        doctor.assert_called_once_with(Path("artifacts"), desktop_probe=True)

    def test_help_excludes_legacy_diagnose_commands(self) -> None:
        help_text = CliRunner().invoke(app, ["--help"]).output

        self.assertIn("doctor", help_text)
        self.assertNotIn("diagnose", help_text)

    def test_chat_flag_starts_cli_first_frontend(self) -> None:
        with patch("max_agent.cli.run_prompt_toolkit_console") as start_chat:
            result = CliRunner().invoke(app, ["--chat"])

        self.assertEqual(result.exit_code, 0)
        start_chat.assert_called_once()

    def test_no_command_starts_cli_first_frontend(self) -> None:
        with patch("max_agent.cli.run_prompt_toolkit_console") as start_chat:
            result = CliRunner().invoke(app, [])

        self.assertEqual(result.exit_code, 0)
        start_chat.assert_called_once()

    def test_fallback_remains_compatibility_alias(self) -> None:
        with patch("max_agent.cli.run_prompt_toolkit_console") as start_console:
            result = CliRunner().invoke(app, ["--fallback"])

        self.assertEqual(result.exit_code, 0)
        start_console.assert_called_once()

    def test_textual_is_explicit_optional_frontend(self) -> None:
        with patch("max_agent.cli.run_textual_chat") as start_textual:
            result = CliRunner().invoke(app, ["--textual"])

        self.assertEqual(result.exit_code, 0)
        start_textual.assert_called_once()

    def test_cli_first_frontend_does_not_require_textual(self) -> None:
        with patch.dict(sys.modules, {"textual": None}), patch("max_agent.cli.run_prompt_toolkit_console") as start_console:
            result = CliRunner().invoke(app, [])

        self.assertEqual(result.exit_code, 0)
        start_console.assert_called_once()

    def test_download_model_command_advertises_qwen35(self) -> None:
        help_text = CliRunner().invoke(app, ["--help"]).output

        self.assertIn("Qwen3.5-4B", help_text)

    def test_cli_advertises_metadata_validation_command(self) -> None:
        help_text = CliRunner().invoke(app, ["--help"]).output

        self.assertIn("validate-model", help_text)
