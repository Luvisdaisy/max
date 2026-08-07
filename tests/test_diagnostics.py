import unittest

from max_agent.diagnostics import (
    CheckResult,
    DiagnosticProbe,
    foreground_probe_skip_detail,
    is_foreground_window,
    render_doctor,
    request_foreground_window,
    run_diagnostics,
)

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

    def test_doctor_summary_groups_runtime_and_tool_checks(self) -> None:
        probe = DiagnosticProbe(
            python_version=lambda: "3.12.13",
            package_versions=lambda: {"torch": "2.13.0+cu130"},
            cuda_available=lambda: True,
            cuda_version=lambda: "13.0",
            bf16_probe=lambda: None,
            dependency_check=lambda: [],
            gpu_name=lambda: "RTX 5070 Ti",
            tool_checks=lambda: [
                CheckResult("mss", "passed", "1920x1080 screenshot captured"),
                CheckResult("desktop_probe", "skipped", "Use --desktop-probe in an interactive session."),
            ],
        )

        result = run_diagnostics(probe)
        output = render_doctor(result)

        self.assertTrue(result.ok)
        self.assertEqual(result.gpu_name, "RTX 5070 Ti")
        self.assertIn("通过", output)
        self.assertIn("跳过", output)
        self.assertNotIn("模型", result.to_dict())

    def test_foreground_window_requires_exact_window_handle(self) -> None:
        self.assertTrue(is_foreground_window(7, lambda: 7))
        self.assertFalse(is_foreground_window(7, lambda: 8))

    def test_desktop_probe_requests_its_own_window_before_handle_confirmation(self) -> None:
        requested: list[int] = []

        request_foreground_window(7, requested.append)

        self.assertEqual(requested, [7])
        self.assertFalse(is_foreground_window(7, lambda: 8))

    def test_foreground_skip_detail_confirms_no_input_was_sent(self) -> None:
        detail = foreground_probe_skip_detail()

        self.assertIn("no desktop input was sent", detail)
        self.assertIn("interactive Windows session", detail)
