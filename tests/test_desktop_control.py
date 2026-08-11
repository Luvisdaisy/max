"""验证模型动作必须经 Guard 且执行前重新核对窗口与时效。"""

import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from max_agent.orchestration.models import (
    ApprovedAction,
    DesktopAction,
    ScreenBounds,
    StandardObservation,
    WindowIdentity,
    action_hash,
)
from max_agent.tools.base import ToolFailureCode
from max_agent.tools.control import (
    ExecuteActionTool,
    GuardActionTool,
    PyAutoGuiDesktopAdapter,
)


def _window() -> WindowIdentity:
    return WindowIdentity(
        hwnd=7,
        process_id=42,
        executable_path="C:/Windows/System32/notepad.exe",
        title="Notes",
    )


def _observation() -> StandardObservation:
    window = _window()
    return StandardObservation(
        captured_at=time.time(),
        bounds=ScreenBounds(left=0, top=0, width=1920, height=1080),
        dpi=96,
        foreground_window=window,
        windows=[
            {
                **window.model_dump(),
                "bounds": {"left": 100, "top": 100, "width": 800, "height": 600},
                "foreground": True,
            }
        ],
        fingerprint="fresh",
    )


class _Adapter:
    def __init__(self) -> None:
        self.actions: list[DesktopAction] = []
        self.releases = 0
        self.foreground = _window().model_dump()
        self.failure: Exception | None = None

    def execute(self, action: DesktopAction) -> None:
        if self.failure:
            raise self.failure
        self.actions.append(action)

    def foreground_identity(self):
        return self.foreground

    def release_all(self) -> None:
        self.releases += 1


class DesktopControlTests(unittest.TestCase):
    def test_activate_restores_minimized_window_before_foreground(self) -> None:
        """任务栏窗口必须先恢复，后续坐标才能绑定可见客户区。"""
        calls: list[tuple[str, int, int | None]] = []
        user32 = SimpleNamespace(
            ShowWindow=lambda hwnd, command: calls.append(("restore", hwnd, command)),
            SetForegroundWindow=lambda hwnd: (
                calls.append(("foreground", hwnd, None)) or True
            ),
        )
        pyautogui = SimpleNamespace(FAILSAFE=False)
        with (
            patch("ctypes.windll.user32", user32),
            patch.dict("sys.modules", {"pyautogui": pyautogui}),
        ):
            PyAutoGuiDesktopAdapter().execute(
                DesktopAction(kind="activate_window", window=_window())
            )

        self.assertTrue(pyautogui.FAILSAFE)
        self.assertEqual(calls, [("restore", 7, 9), ("foreground", 7, None)])

    def test_type_text_uses_unicode_packets_and_return_key(self) -> None:
        """文本输入必须脱离键盘布局与 IME，并保留标准换行。"""
        captured: list[tuple[int, int, int]] = []

        def send_input(count, batch, size):
            captured.extend(
                (
                    int(batch[index].keyboard.virtual_key),
                    int(batch[index].keyboard.scan_code),
                    int(batch[index].keyboard.flags),
                )
                for index in range(count)
            )
            return count

        pyautogui = SimpleNamespace(FAILSAFE=False)
        with (
            patch("ctypes.windll.user32", SimpleNamespace(SendInput=send_input)),
            patch.dict("sys.modules", {"pyautogui": pyautogui}),
        ):
            PyAutoGuiDesktopAdapter().execute(
                DesktopAction(kind="type_text", text="AΩ\n")
            )

        self.assertEqual(
            captured,
            [
                (0, ord("A"), 0x0004),
                (0, ord("A"), 0x0004 | 0x0002),
                (0, ord("Ω"), 0x0004),
                (0, ord("Ω"), 0x0004 | 0x0002),
                (0x0D, 0, 0),
                (0x0D, 0, 0x0002),
            ],
        )

    def test_release_all_bypasses_failsafe_to_release_every_input_state(self) -> None:
        """紧急中止后仍必须释放修饰键和鼠标键。"""
        keyboard: list[tuple[int, int]] = []
        mouse: list[int] = []
        user32 = SimpleNamespace(
            keybd_event=lambda key, scan, flags, extra: keyboard.append((key, flags)),
            mouse_event=lambda flags, dx, dy, data, extra: mouse.append(flags),
        )
        with patch("ctypes.windll.user32", user32):
            PyAutoGuiDesktopAdapter().release_all()

        self.assertEqual(
            keyboard,
            [
                (0x11, 0x0002),
                (0x12, 0x0002),
                (0x10, 0x0002),
                (0x5B, 0x0002),
                (0x5C, 0x0002),
            ],
        )
        self.assertEqual(mouse, [0x0004 | 0x0010 | 0x0040])

    def test_guard_binds_valid_action_to_window_fingerprint_and_expiry(self) -> None:
        action = DesktopAction(kind="click", window=_window(), x=200, y=250)
        receipt = GuardActionTool().invoke(
            GuardActionTool.input_model(action=action, observation=_observation())
        )
        approved = ApprovedAction.model_validate(receipt.data["approved"])
        self.assertTrue(receipt.success)
        self.assertEqual(approved.action_hash, action_hash(action))
        self.assertEqual(approved.state_fingerprint, "fresh")
        self.assertGreater(approved.expires_at, approved.approved_at)

    def test_guard_converts_normalized_coordinates_to_target_physical_pixels(
        self,
    ) -> None:
        action = DesktopAction(
            kind="click",
            window=_window(),
            x=500,
            y=500,
            coordinate_space="normalized_1000",
        )
        receipt = GuardActionTool().invoke(
            GuardActionTool.input_model(action=action, observation=_observation())
        )
        approved = ApprovedAction.model_validate(receipt.data["approved"])
        self.assertEqual((approved.physical_x, approved.physical_y), (500, 400))
        self.assertEqual((approved.action.x, approved.action.y), (500, 400))

    def test_guard_rejects_stale_window_coordinates_and_key_chord(self) -> None:
        observation = _observation()
        cases = (
            DesktopAction(
                kind="click",
                window=WindowIdentity(
                    hwnd=8, process_id=42, executable_path=_window().executable_path
                ),
                x=200,
                y=250,
            ),
            DesktopAction(kind="click", window=_window(), x=20, y=20),
            DesktopAction(
                kind="key_chord", window=_window(), keys=["ctrl", "shift", "x"]
            ),
        )
        for action in cases:
            with self.subTest(action=action.kind):
                receipt = GuardActionTool().invoke(
                    GuardActionTool.input_model(action=action, observation=observation)
                )
                self.assertFalse(receipt.success)

    def test_high_impact_save_waits_for_user_but_notepad_text_can_run(self) -> None:
        observation = _observation()
        save = GuardActionTool().invoke(
            GuardActionTool.input_model(
                action=DesktopAction(
                    kind="key_chord", window=_window(), keys=["ctrl", "s"]
                ),
                observation=observation,
            )
        )
        append = GuardActionTool().invoke(
            GuardActionTool.input_model(
                action=DesktopAction(
                    kind="type_text", window=_window(), text="新增内容"
                ),
                observation=observation,
            )
        )
        self.assertTrue(save.data["requires_user"])
        self.assertIn("approved", append.data)

    def test_execute_rechecks_fingerprint_focus_and_expiry(self) -> None:
        adapter = _Adapter()
        action = DesktopAction(kind="type_text", window=_window(), text="新增内容")
        now = time.monotonic()
        approved = ApprovedAction(
            action=action,
            action_hash=action_hash(action),
            state_fingerprint="fresh",
            approved_at=now,
            expires_at=now + 2,
        )
        tool = ExecuteActionTool(adapter)
        success = tool.invoke(
            tool.input_model(approved=approved, current_fingerprint="fresh")
        )
        self.assertTrue(success.success)
        self.assertEqual(success.data["input_length"], 4)
        adapter.foreground = {**adapter.foreground, "hwnd": 8}
        stale = tool.invoke(
            tool.input_model(approved=approved, current_fingerprint="fresh")
        )
        self.assertEqual(stale.error.code, ToolFailureCode.STALE_TARGET)

    def test_action_exception_releases_input_and_never_retries(self) -> None:
        adapter = _Adapter()
        adapter.failure = RuntimeError("boom")
        action = DesktopAction(kind="click", window=_window(), x=200, y=200)
        now = time.monotonic()
        approved = ApprovedAction(
            action=action,
            action_hash=action_hash(action),
            state_fingerprint="fresh",
            approved_at=now,
            expires_at=now + 2,
        )
        receipt = ExecuteActionTool(adapter).invoke(
            ExecuteActionTool.input_model(
                approved=approved, current_fingerprint="fresh"
            )
        )
        self.assertEqual(receipt.error.code, ToolFailureCode.EXECUTION_FAILED)
        self.assertEqual(adapter.releases, 1)
        self.assertEqual(adapter.actions, [])


if __name__ == "__main__":
    unittest.main()
