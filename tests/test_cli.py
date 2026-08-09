import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from max_agent.cli import _doctor_operation, main
from max_agent.diagnostics import DiagnosticResult


class CliTests(unittest.TestCase):
    def test_default_and_chat_start_the_same_textual_interface(self) -> None:
        with patch("max_agent.cli.run_textual_chat") as start_chat:
            main([])
            main(["--chat"])

        self.assertEqual(start_chat.call_count, 2)

    def test_removed_cli_operations_are_rejected(self) -> None:
        for operation in (
            "doctor",
            "download-model",
            "--doctor",
            "--fallback",
            "--textual",
        ):
            with self.subTest(operation=operation), self.assertRaises(SystemExit):
                main([operation])

    def test_help_does_not_advertise_removed_operations(self) -> None:
        with self.assertRaises(SystemExit):
            main(["--help"])

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
