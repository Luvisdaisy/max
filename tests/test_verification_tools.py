"""验证动作结果、有限恢复与归档脱敏边界。"""

import tempfile
import time
import unittest
from pathlib import Path

from max_agent.orchestration.models import (
    DesktopAction,
    ScreenBounds,
    StandardObservation,
    WindowIdentity,
)
from max_agent.tools.verification import ArchiveRunTool, RecoverTool, VerifyResultTool


def _window(hwnd: int = 7) -> WindowIdentity:
    return WindowIdentity(
        hwnd=hwnd,
        process_id=42,
        executable_path="C:/Windows/System32/notepad.exe",
        title="未命名 - 记事本",
    )


def _observation(
    fingerprint: str,
    *,
    text: str = "",
    foreground: WindowIdentity | None = None,
) -> StandardObservation:
    return StandardObservation(
        captured_at=time.time(),
        bounds=ScreenBounds(left=0, top=0, width=1000, height=800),
        foreground_window=foreground or _window(),
        ocr_lines=[
            {
                "text": text,
                "bounds": {"left": 20, "top": 30, "width": 200, "height": 30},
            }
        ],
        fingerprint=fingerprint,
        changed_regions=[ScreenBounds(left=20, top=30, width=200, height=30)]
        if fingerprint not in {"before", "same"}
        else [],
    )


class VerificationToolTests(unittest.TestCase):
    def test_notepad_text_requires_fresh_ocr_and_target_foreground(self) -> None:
        action = DesktopAction(kind="type_text", window=_window(), text="新的验收标记")
        verified = VerifyResultTool().invoke(
            VerifyResultTool.input_model(
                user_goal="追加内容",
                action=action,
                before=_observation("before", text="旧内容"),
                after=_observation("after", text="旧内容\n新的验收标记"),
            )
        )
        self.assertTrue(verified.data["completed"])
        self.assertGreater(verified.data["changed_ratio"], 0)
        self.assertTrue(
            any(
                item.startswith("ocr_contains_input_sha256:")
                for item in verified.data["evidence"]
            )
        )

        wrong_window = VerifyResultTool().invoke(
            VerifyResultTool.input_model(
                user_goal="追加内容",
                action=action,
                before=_observation("before", text="旧内容"),
                after=_observation("after", text="新的验收标记", foreground=_window(9)),
            )
        )
        self.assertFalse(wrong_window.data["completed"])

    def test_notepad_ocr_contains_text_across_layout_whitespace_and_case(self) -> None:
        """OCR 可能重排行或改变大小写，但不得丢失实际字符。"""
        action = DesktopAction(
            kind="type_text", window=_window(), text="\nMAX AGENT RUNTIME PASS"
        )
        receipt = VerifyResultTool().invoke(
            VerifyResultTool.input_model(
                user_goal="追加内容",
                action=action,
                before=_observation("before", text="旧内容"),
                after=_observation("after", text="旧内容\nmaxagentruntime pass"),
            )
        )

        self.assertTrue(receipt.data["completed"])

    def test_execution_receipt_or_character_count_cannot_verify_text(self) -> None:
        action = DesktopAction(
            kind="type_text", window=_window(), text="只发出了输入事件"
        )
        receipt = VerifyResultTool().invoke(
            VerifyResultTool.input_model(
                user_goal="追加内容",
                action=action,
                before=_observation("before", text="旧内容"),
                after=_observation("after", text="旧内容"),
            )
        )
        self.assertFalse(receipt.data["completed"])
        self.assertFalse(receipt.data["no_progress"])

    def test_unchanged_observation_is_no_progress(self) -> None:
        action = DesktopAction(kind="click", window=_window(), x=100, y=100)
        receipt = VerifyResultTool().invoke(
            VerifyResultTool.input_model(
                user_goal="聚焦编辑区",
                action=action,
                before=_observation("same"),
                after=_observation("same"),
            )
        )
        self.assertFalse(receipt.data["completed"])
        self.assertTrue(receipt.data["no_progress"])

    def test_recovery_transitions_are_bounded_and_never_execute_actions(self) -> None:
        tool = RecoverTool()
        decisions = [
            tool.invoke(
                tool.input_model(no_progress_count=count, remaining_recoveries=3)
            ).data["decision"]
            for count in (1, 2, 3)
        ]
        self.assertEqual(decisions, ["reobserve", "deliberate_reason", "wait_user"])
        exhausted = tool.invoke(
            tool.input_model(no_progress_count=0, remaining_recoveries=0)
        )
        self.assertEqual(exhausted.data["decision"], "fail")

    def test_archive_drops_screenshots_ocr_input_password_and_raw_model_data(
        self,
    ) -> None:
        secret = "SENSITIVE-SENTINEL-4937"
        with tempfile.TemporaryDirectory() as temporary:
            tool = ArchiveRunTool(Path(temporary))
            receipt = tool.invoke(
                tool.input_model(
                    task_id="task-1",
                    status="succeeded",
                    config={"password": secret, "safe_mode": True},
                    trajectory=[
                        {
                            "screenshot": secret,
                            "text": secret,
                            "clipboard": secret,
                            "model_response": secret,
                            "phase": "verify",
                        }
                    ],
                    result={
                        "input_text": secret,
                        "raw": secret,
                        "response_text": secret,
                        "user_goal": secret,
                        "status": "succeeded",
                    },
                )
            )
            self.assertTrue(receipt.success)
            archive_files = list(Path(temporary).rglob("*"))
            contents = "\n".join(
                path.read_text(encoding="utf-8")
                for path in archive_files
                if path.is_file()
            )
            self.assertNotIn(secret, contents)
            self.assertIn("verify", contents)
            self.assertIn("succeeded", contents)


if __name__ == "__main__":
    unittest.main()
