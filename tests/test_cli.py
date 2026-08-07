import unittest
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

    def test_chat_flag_starts_default_frontend(self) -> None:
        with patch("max_agent.cli.run_textual_chat") as start_chat:
            result = CliRunner().invoke(app, ["--chat"])

        self.assertEqual(result.exit_code, 0)
        start_chat.assert_called_once()

    def test_download_model_command_advertises_qwen35(self) -> None:
        help_text = CliRunner().invoke(app, ["--help"]).output

        self.assertIn("Qwen3.5-4B", help_text)

    def test_cli_advertises_metadata_validation_command(self) -> None:
        help_text = CliRunner().invoke(app, ["--help"]).output

        self.assertIn("validate-model", help_text)
