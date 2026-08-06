import unittest

from max_agent.diagnostics import DiagnosticProbe, run_diagnostics

class DiagnosticTests(unittest.TestCase):
    def test_diagnostics_reports_successful_cuda_bf16_probe(self) -> None:
        probe = DiagnosticProbe(
            python_version=lambda: "3.12.13",
            package_versions=lambda: {"torch": "2.13.0+cu130"},
            cuda_available=lambda: True,
            cuda_version=lambda: "13.0",
            bf16_probe=lambda: None,
            dependency_check=lambda: [],
        )

        result = run_diagnostics(probe)

        self.assertTrue(result.ok)
        self.assertTrue(result.cuda_available)
        self.assertEqual(result.cuda_version, "13.0")
        self.assertTrue(result.bf16_supported)
        self.assertEqual(result.failures, [])

    def test_diagnostics_marks_failed_bf16_probe_as_non_compliant(self) -> None:
        probe = DiagnosticProbe(
            python_version=lambda: "3.12.13",
            package_versions=lambda: {"torch": "2.13.0+cu130"},
            cuda_available=lambda: True,
            cuda_version=lambda: "13.0",
            bf16_probe=lambda: (_ for _ in ()).throw(RuntimeError("unsupported")),
            dependency_check=lambda: [],
        )

        result = run_diagnostics(probe)

        self.assertFalse(result.ok)
        self.assertFalse(result.bf16_supported)
        self.assertEqual(result.failures, ["BF16 CUDA tensor operation failed: unsupported"])
