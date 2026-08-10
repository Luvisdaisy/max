"""验证 UI 无关的聊天文本与斜杠命令分发结果。"""

import unittest

from max_agent.console_core import OperationResult, dispatch_input


class ConsoleCoreTests(unittest.TestCase):
    def test_chat_message_uses_local_runtime_handler(self) -> None:
        result = dispatch_input("hello", chat=lambda text: f"reply:{text}")

        self.assertEqual(result.kind, "chat")
        self.assertEqual(result.messages[-1], "reply:hello")
        self.assertFalse(result.should_exit)

    def test_chat_runtime_error_keeps_session_open(self) -> None:
        result = dispatch_input(
            "hello",
            chat=lambda text: (_ for _ in ()).throw(RuntimeError("offline failure")),
        )

        self.assertEqual(result.kind, "runtime_error")
        self.assertFalse(result.should_exit)

    def test_quit_command_requests_exit(self) -> None:
        result = dispatch_input("/quit")

        self.assertTrue(result.should_exit)

    def test_doctor_command_uses_doctor_handler(self) -> None:
        result = dispatch_input("/doctor", doctor=lambda: "doctor-result")

        self.assertEqual(result, "doctor-result")

    def test_model_commands_use_model_handler_without_chat(self) -> None:
        selections: list[str | None] = []
        result = dispatch_input(
            "/model Qwen/Qwen3.5-4B",
            model=lambda name: (
                selections.append(name) or OperationResult("model", ("selected",))
            ),
            chat=lambda text: self.fail("model command must not start chat"),
        )

        self.assertEqual(selections, ["Qwen/Qwen3.5-4B"])
        self.assertEqual(result.kind, "model")

    def test_model_list_uses_none_selection(self) -> None:
        result = dispatch_input(
            "/model", model=lambda name: OperationResult("model", (str(name),))
        )

        self.assertEqual(result.messages, ("None",))

    def test_legacy_diagnose_command_is_unsupported(self) -> None:
        result = dispatch_input("/diagnose")

        self.assertEqual(result.kind, "command_error")

    def test_unknown_command_keeps_session_open(self) -> None:
        result = dispatch_input("/unknown")

        self.assertIn("Unsupported command", result.messages[-1])
        self.assertFalse(result.should_exit)
