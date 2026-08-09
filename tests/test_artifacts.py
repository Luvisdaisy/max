import json
import tempfile
import unittest
from pathlib import Path

from max_agent.artifacts import ExperimentArchive


class ArtifactTests(unittest.TestCase):
    def test_archive_writes_required_evidence_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = ExperimentArchive.create(Path(directory), "diagnose")

            archive.write_config({"command": "diagnose"})
            archive.write_environment({"cuda_available": True})
            archive.append_trajectory({"event": "started"})
            archive.write_result({"status": "success"})

            self.assertTrue((archive.path / "config.yaml").is_file())
            self.assertEqual(
                json.loads(
                    (archive.path / "environment.json").read_text(encoding="utf-8")
                ),
                {"cuda_available": True},
            )
            self.assertEqual(
                (archive.path / "trajectory.jsonl").read_text(encoding="utf-8"),
                '{"event": "started"}\n',
            )
            self.assertEqual(
                json.loads((archive.path / "result.json").read_text(encoding="utf-8")),
                {"status": "success"},
            )
