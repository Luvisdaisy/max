from pathlib import Path
import tempfile
import unittest

from max_agent.artifacts import ExperimentArchive
from max_agent.benchmark import run_benchmark


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_records_load_memory_latency_and_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = ExperimentArchive.create(Path(directory), "benchmark")

            result = run_benchmark(
                archive=archive,
                config={"model": "local"},
                environment={"cuda_available": True},
                load_model=lambda: "model",
                infer=lambda model: {"text": f"{model}-result"},
                peak_memory_bytes=lambda: 1024,
            )

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["peak_gpu_memory_bytes"], 1024)
            self.assertEqual(result["output"], {"text": "model-result"})
            self.assertTrue((archive.path / "result.json").is_file())
            self.assertEqual((archive.path / "environment.json").read_text(encoding="utf-8"), '{"cuda_available": true}\n')
