"""验证基准成功与各失败阶段均写入脱敏且完整的归档证据。"""

import json
import tempfile
import unittest
from pathlib import Path

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
            self.assertEqual(result["stage"], "completed")
            self.assertTrue(result["offline"])
            self.assertEqual(result["peak_gpu_memory_bytes"], 1024)
            self.assertEqual(result["output"], {"text": "model-result"})
            self.assertTrue((archive.path / "result.json").is_file())
            self.assertEqual(
                (archive.path / "environment.json").read_text(encoding="utf-8"),
                '{"cuda_available": true}\n',
            )

    def test_preflight_failure_is_archived_without_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = ExperimentArchive.create(Path(directory), "benchmark")

            with self.assertRaisesRegex(ValueError, "invalid image"):
                run_benchmark(
                    archive=archive,
                    config={"offline": True},
                    environment={},
                    preflight=lambda: (_ for _ in ()).throw(
                        ValueError("invalid image at C:\\Users\\admin\\private.png")
                    ),
                    load_model=lambda: self.fail("load must not run"),
                    infer=lambda model: self.fail("infer must not run"),
                    peak_memory_bytes=lambda: 0,
                )

            result = json.loads(
                (archive.path / "result.json").read_text(encoding="utf-8")
            )
            trajectory = (archive.path / "trajectory.jsonl").read_text(encoding="utf-8")
            self.assertEqual(result["stage"], "preflight")
            self.assertTrue(result["offline"])
            self.assertNotIn("C:\\Users", result["error"])
            self.assertNotIn("C:\\Users", trajectory)

    def test_load_and_inference_failures_record_their_stage(self) -> None:
        for stage, load_model, infer in (
            (
                "load",
                lambda: (_ for _ in ()).throw(RuntimeError("load failed")),
                lambda model: {},
            ),
            (
                "inference",
                lambda: "model",
                lambda model: (_ for _ in ()).throw(RuntimeError("inference failed")),
            ),
        ):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory:
                archive = ExperimentArchive.create(Path(directory), "benchmark")

                with self.assertRaises(RuntimeError):
                    run_benchmark(
                        archive=archive,
                        config={"offline": True},
                        environment={},
                        load_model=load_model,
                        infer=infer,
                        peak_memory_bytes=lambda: 0,
                    )

                result = json.loads(
                    (archive.path / "result.json").read_text(encoding="utf-8")
                )
                self.assertEqual(result["stage"], stage)
