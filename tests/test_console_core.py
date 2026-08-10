"""验证 UI 无关的结构化会话事件与斜杠命令分发。"""

import unittest

from max_agent.console_core import (
    COMMAND_SPECS,
    ConsoleEvent,
    ConsoleEventKind,
    OperationResult,
    dispatch_input,
)


class ConsoleCoreTests(unittest.TestCase):
    """确保命令与聊天共享协议，但不会相互误触发。"""

    def test_chat_returns_only_assistant_event(self) -> None:
        result = dispatch_input("hello", chat=lambda text, emit: f"reply:{text}")

        self.assertEqual(result.kind, "chat")
        self.assertEqual(
            result.events, (ConsoleEvent(ConsoleEventKind.ASSISTANT, "reply:hello"),)
        )
        self.assertNotIn("hello", [event.text for event in result.events[:-1]])
        self.assertFalse(result.should_exit)

    def test_chat_runtime_error_keeps_session_open(self) -> None:
        result = dispatch_input(
            "hello",
            chat=lambda text, emit: (_ for _ in ()).throw(
                RuntimeError("offline failure")
            ),
        )

        self.assertEqual(result.events[-1].kind, ConsoleEventKind.ERROR)
        self.assertIn("offline failure", result.events[-1].text)
        self.assertFalse(result.should_exit)

    def test_quit_command_requests_exit(self) -> None:
        result = dispatch_input("/quit")

        self.assertTrue(result.should_exit)

    def test_doctor_command_uses_doctor_handler(self) -> None:
        expected = OperationResult(
            "doctor", (ConsoleEvent(ConsoleEventKind.COMMAND, "doctor-result"),)
        )
        result = dispatch_input("/doctor", doctor=lambda: expected)

        self.assertEqual(result, expected)

    def test_model_commands_use_model_handler_without_chat(self) -> None:
        selections: list[str | None] = []
        result = dispatch_input(
            "/model Qwen/Qwen3.5-4B",
            model=lambda name: (
                selections.append(name)
                or OperationResult(
                    "model", (ConsoleEvent(ConsoleEventKind.COMMAND, "selected"),)
                )
            ),
            chat=lambda text, emit: self.fail("模型命令不得启动聊天"),
        )

        self.assertEqual(selections, ["Qwen/Qwen3.5-4B"])
        self.assertEqual(result.kind, "model")

    def test_model_list_uses_none_selection(self) -> None:
        result = dispatch_input(
            "/model",
            model=lambda name: OperationResult(
                "model", (ConsoleEvent(ConsoleEventKind.COMMAND, str(name)),)
            ),
        )

        self.assertEqual(result.events[-1].text, "None")

    def test_help_is_generated_from_shared_command_specs(self) -> None:
        result = dispatch_input("/help")

        for command in COMMAND_SPECS:
            self.assertIn(command.usage, result.events[-1].text)

    def test_clear_delegates_without_starting_chat(self) -> None:
        calls: list[str] = []
        result = dispatch_input(
            "/clear",
            clear=lambda: calls.append("clear"),
            chat=lambda text, emit: self.fail("清除命令不得启动聊天"),
        )

        self.assertEqual(calls, ["clear"])
        self.assertEqual(result.kind, "clear")

    def test_status_uses_status_handler_without_starting_chat(self) -> None:
        expected = OperationResult(
            "status", (ConsoleEvent(ConsoleEventKind.COMMAND, "ready"),)
        )
        result = dispatch_input(
            "/status",
            status=lambda: expected,
            chat=lambda text, emit: self.fail("状态命令不得启动聊天"),
        )

        self.assertEqual(result, expected)

    def test_all_supported_commands_avoid_chat_handler(self) -> None:
        def no_chat(text, emit):
            self.fail(f"斜杠命令误触发聊天：{text}")

        for value in ("/help", "/status", "/model", "/doctor", "/clear", "/quit"):
            with self.subTest(value=value):
                dispatch_input(value, chat=no_chat)

    def test_unknown_command_keeps_session_open_and_suggests_help(self) -> None:
        result = dispatch_input("/unknown")

        self.assertEqual(result.events[-1].kind, ConsoleEventKind.ERROR)
        self.assertIn("/help", result.events[-1].text)
        self.assertFalse(result.should_exit)


if __name__ == "__main__":
    unittest.main()
