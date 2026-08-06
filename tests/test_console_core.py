import unittest

from max_agent.console_core import dispatch_input


class ConsoleCoreTests(unittest.TestCase):
    def test_chat_message_reports_unconfigured_backend(self) -> None:
        result = dispatch_input("hello")

        self.assertEqual(result.kind, "chat")
        self.assertIn("AI backend is not configured", result.messages[-1])
        self.assertFalse(result.should_exit)

    def test_quit_command_requests_exit(self) -> None:
        result = dispatch_input("/quit")

        self.assertTrue(result.should_exit)

    def test_unknown_command_keeps_session_open(self) -> None:
        result = dispatch_input("/unknown")

        self.assertIn("Unsupported command", result.messages[-1])
        self.assertFalse(result.should_exit)

