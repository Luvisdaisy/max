"""验证诊断汇总及 Windows 桌面探针的安全边界与失败呈现。"""

import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from max_agent.diagnostics import (
    CheckResult,
    DiagnosticProbe,
    _check_desktop_probe,
    enable_per_monitor_dpi_awareness,
    foreground_probe_skip_detail,
    is_foreground_window,
    render_doctor,
    request_controlled_foreground_window,
    request_foreground_window,
    run_diagnostics,
    send_controlled_click,
    send_controlled_text,
    wait_for_foreground_window,
    wait_for_probe_condition,
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
        self.assertEqual(
            result.failures, ["BF16 CUDA tensor operation failed: unsupported"]
        )

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
                CheckResult(
                    "desktop_probe",
                    "skipped",
                    "Use --desktop-probe in an interactive session.",
                ),
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

    def test_desktop_probe_requests_per_monitor_v2_dpi_awareness(self) -> None:
        contexts: list[int] = []

        enable_per_monitor_dpi_awareness(contexts.append)

        self.assertEqual(contexts, [-4])

    def test_controlled_text_checks_every_unicode_sendinput_event(self) -> None:
        calls: list[tuple[int, int]] = []

        class User32:
            def SendInput(self, count: int, events: object, size: int) -> int:
                calls.append((count, size))
                return count

        send_controlled_text("doctor", User32())

        self.assertEqual(calls[0][0], 12)

    def test_controlled_click_moves_cursor_and_checks_both_events(self) -> None:
        calls: list[tuple[object, ...]] = []

        class User32:
            def SetCursorPos(self, x: int, y: int) -> int:
                calls.append(("move", x, y))
                return 1

            def SendInput(self, count: int, events: object, size: int) -> int:
                calls.append(("input", count))
                return count

        send_controlled_click((10, 20), User32())

        self.assertEqual(calls, [("move", 10, 20), ("input", 2)])

    def test_controlled_input_reports_partial_sendinput_failure(self) -> None:
        class User32:
            def SendInput(self, count: int, events: object, size: int) -> int:
                return count - 1

        with self.assertRaisesRegex(RuntimeError, "inserted 11 of 12"):
            send_controlled_text("doctor", User32())

    def test_desktop_probe_reports_native_worker_crash(self) -> None:
        crashed = CompletedProcess([], 0xC000041D, "", "")

        with patch("max_agent.diagnostics.subprocess.run", return_value=crashed):
            result = _check_desktop_probe()

        self.assertEqual(result.status, "failed")
        self.assertIn("0xC000041D", result.detail)

    def test_desktop_probe_accepts_worker_result(self) -> None:
        completed = CompletedProcess(
            [],
            0,
            '{"name":"desktop_probe","status":"passed","detail":"verified"}',
            "",
        )

        with patch("max_agent.diagnostics.subprocess.run", return_value=completed):
            result = _check_desktop_probe()

        self.assertEqual(result, CheckResult("desktop_probe", "passed", "verified"))

    def test_probe_condition_pumps_messages_until_state_changes(self) -> None:
        state = {"focused": False}

        def pump() -> None:
            state["focused"] = True

        focused = wait_for_probe_condition(lambda: state["focused"], pump)

        self.assertTrue(focused)

    def test_foreground_wait_pumps_events_without_sending_input(self) -> None:
        events: list[str] = []
        windows = iter((8, 7))

        focused = wait_for_foreground_window(
            7,
            lambda: next(windows),
            lambda: events.append("pump"),
            time_fn=iter((0.0, 0.1)).__next__,
            sleep=lambda seconds: events.append("sleep"),
        )

        self.assertTrue(focused)
        self.assertEqual(events, ["pump", "sleep", "pump"])

    def test_desktop_probe_requests_its_own_window_before_handle_confirmation(
        self,
    ) -> None:
        requested: list[int] = []

        request_foreground_window(7, requested.append)

        self.assertEqual(requested, [7])
        self.assertFalse(is_foreground_window(7, lambda: 8))

    def test_controlled_foreground_request_only_attaches_to_current_foreground_thread(
        self,
    ) -> None:
        calls: list[tuple[object, ...]] = []

        class User32:
            def GetForegroundWindow(self) -> int:
                return 9

            def GetWindowThreadProcessId(self, window: int, process: object) -> int:
                return 4

            def AttachThreadInput(
                self, current: int, foreground: int, attach: bool
            ) -> int:
                calls.append(("attach", current, foreground, attach))
                return 1

            def BringWindowToTop(self, window: int) -> None:
                calls.append(("top", window))

            def SetForegroundWindow(self, window: int) -> None:
                calls.append(("foreground", window))

        request_controlled_foreground_window(7, User32(), lambda: 3)

        self.assertEqual(
            calls,
            [
                ("attach", 3, 4, True),
                ("top", 7),
                ("foreground", 7),
                ("attach", 3, 4, False),
            ],
        )

    def test_foreground_skip_detail_confirms_no_input_was_sent(self) -> None:
        detail = foreground_probe_skip_detail()

        self.assertIn("no desktop input was sent", detail)
        self.assertIn("interactive Windows session", detail)
