from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class QualityConfigurationTests(unittest.TestCase):
    def test_ruff_is_pinned_and_targets_python_312(self) -> None:
        requirements = (REPOSITORY_ROOT / "requirements.txt").read_text(
            encoding="utf-8"
        )
        pyproject = tomllib.loads(
            (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )

        self.assertIn("ruff==0.16.2", requirements)
        self.assertEqual(pyproject["tool"]["ruff"]["target-version"], "py312")
        self.assertEqual(pyproject["tool"]["ruff"]["lint"]["select"], ["F", "I"])

    def test_ci_runs_the_windows_quality_gate_without_model_commands(self) -> None:
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "quality.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("push:", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertIn("runs-on: windows-latest", workflow)
        self.assertIn('python-version: "3.12"', workflow)
        self.assertIn("ruff format --check src tests", workflow)
        self.assertIn("ruff check src tests", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        self.assertIn("python -m pip check", workflow)
        for forbidden in ("max-agent", "download-model", "benchmark", "model/"):
            self.assertNotIn(forbidden, workflow)
