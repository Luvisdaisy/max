import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from max_agent.cli import app


class CliTests(unittest.TestCase):
    def test_diagnose_flag_dispatches_non_interactive_operation(self) -> None:
        with patch("max_agent.cli._diagnose", return_value=0) as diagnose:
            result = CliRunner().invoke(app, ["--diagnose"])

        self.assertEqual(result.exit_code, 0)
        diagnose.assert_called_once()

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
