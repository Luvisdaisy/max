import unittest

from max_agent.console_core import OperationResult
from max_agent.console_frontends import run_line_console


class ConsoleFrontendTests(unittest.TestCase):
    def test_line_console_dispatches_and_exits_on_quit(self) -> None:
        lines = iter(["hello", "/quit"])
        rendered: list[str] = []

        run_line_console(
            read_line=lambda: next(lines),
            dispatch=lambda value: OperationResult("quit", (value,), should_exit=value == "/quit"),
            render=rendered.append,
        )

        self.assertEqual(rendered, ["hello", "/quit"])
