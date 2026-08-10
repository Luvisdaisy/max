"""验证 Textual 会话工作台的键盘、并发、滚动与安全展示行为。"""

import threading
import unittest

from textual.containers import VerticalScroll
from textual.widgets import Markdown, OptionList, Static, TextArea

from max_agent.console_core import (
    ConsoleEvent,
    ConsoleEventKind,
    OperationResult,
    SessionStatus,
)
from max_agent.console_frontends import create_textual_chat_app


def _result(
    text: str,
    *,
    kind: str = "chat",
    event_kind: ConsoleEventKind = ConsoleEventKind.ASSISTANT,
) -> OperationResult:
    """构造前端测试所需的最小结构化结果。"""
    return OperationResult(kind, (ConsoleEvent(event_kind, text),))


class ConsoleFrontendTests(unittest.IsolatedAsyncioTestCase):
    """使用 Textual headless Pilot 验证用户可观察行为而非像素颜色。"""

    async def test_initial_focus_status_and_markdown_response(self) -> None:
        app = create_textual_chat_app(
            lambda value, emit=None: _result("## 结果\n\n- `ok`"),
            lambda: SessionStatus("Qwen/Test", "ready"),
        )

        async with app.run_test() as pilot:
            self.assertEqual(app.focused.id, "composer")
            self.assertIn(
                "Qwen/Test", str(app.query_one("#model-status", Static).content)
            )
            await pilot.press("h", "i", "enter")
            await pilot.pause()

            self.assertEqual(len(app.query(".user-message")), 1)
            self.assertEqual(len(app.query(".assistant-message")), 1)
            self.assertEqual(len(app.query(Markdown)), 1)
            self.assertEqual(app.focused.id, "composer")

    async def test_multiline_submit_shift_enter_and_local_history(self) -> None:
        calls: list[str] = []
        app = create_textual_chat_app(
            lambda value, emit=None: calls.append(value) or _result("完成")
        )

        async with app.run_test() as pilot:
            await pilot.press("a", "shift+enter", "b", "enter")
            await pilot.pause()
            self.assertEqual(calls, ["a\nb"])

            await pilot.press("ctrl+up")
            self.assertEqual(app.query_one("#composer", TextArea).text, "a\nb")
            await pilot.press("ctrl+down")
            self.assertEqual(app.query_one("#composer", TextArea).text, "")

    async def test_blank_input_is_ignored(self) -> None:
        calls: list[str] = []
        app = create_textual_chat_app(
            lambda value, emit=None: calls.append(value) or _result("unexpected")
        )

        async with app.run_test() as pilot:
            await pilot.press("space", "space", "enter")
            await pilot.pause()

            self.assertEqual(calls, [])
            self.assertEqual(len(app.query(".user-message")), 0)

    async def test_command_menu_filters_completes_and_dispatches(self) -> None:
        calls: list[str] = []
        app = create_textual_chat_app(
            lambda value, emit=None: (
                calls.append(value)
                or _result("ready", kind="status", event_kind=ConsoleEventKind.COMMAND)
            )
        )

        async with app.run_test() as pilot:
            await pilot.press("/", "s", "t")
            menu = app.query_one("#command-menu", OptionList)
            self.assertTrue(menu.has_class("visible"))
            self.assertEqual(menu.option_count, 1)

            await pilot.press("tab")
            self.assertEqual(app.query_one("#composer", TextArea).text, "/status")
            await pilot.press("enter")
            await pilot.pause()

            self.assertEqual(calls, ["/status"])
            self.assertEqual(len(app.query(".command-message")), 1)

    async def test_clear_replaces_transcript_with_fresh_welcome(self) -> None:
        def dispatch(value, emit=None):
            if value == "/clear":
                return _result(
                    "已清空", kind="clear", event_kind=ConsoleEventKind.NOTICE
                )
            return _result("回复")

        app = create_textual_chat_app(dispatch)
        async with app.run_test() as pilot:
            await pilot.press("h", "i", "enter")
            await pilot.pause()
            await pilot.press("/", "c", "l", "e", "a", "r", "enter")
            await pilot.pause()

            transcript = app.query_one("#transcript", VerticalScroll)
            self.assertEqual(len(transcript.children), 1)
            self.assertIn("MAX 已就绪", str(transcript.children[0].content))

    async def test_busy_gate_allows_only_one_dispatch_and_restores_editor(self) -> None:
        started = threading.Event()
        release = threading.Event()
        calls: list[str] = []

        def dispatch(value, emit=None):
            calls.append(value)
            if emit is not None:
                emit(
                    ConsoleEvent(
                        ConsoleEventKind.NOTICE,
                        "正在生成本地回复",
                        state="generating",
                    )
                )
            started.set()
            release.wait(3)
            return _result("完成")

        app = create_textual_chat_app(dispatch)
        try:
            async with app.run_test() as pilot:
                await pilot.press("o", "n", "e", "enter")
                for _ in range(20):
                    if started.is_set():
                        break
                    await pilot.pause(0.02)
                composer = app.query_one("#composer", TextArea)
                self.assertTrue(started.is_set())
                self.assertTrue(composer.disabled)

                await pilot.press("t", "w", "o", "enter")
                self.assertEqual(calls, ["one"])
                self.assertIn("s", str(app.query_one("#activity", Static).content))

                release.set()
                for _ in range(20):
                    await pilot.pause(0.02)
                    if not composer.disabled:
                        break
                self.assertFalse(composer.disabled)
                self.assertEqual(app.focused.id, "composer")
        finally:
            release.set()

    async def test_runtime_failure_uses_error_style_and_restores_editor(self) -> None:
        app = create_textual_chat_app(
            lambda value, emit=None: _result(
                "本地失败",
                kind="runtime_error",
                event_kind=ConsoleEventKind.ERROR,
            )
        )

        async with app.run_test() as pilot:
            await pilot.press("x", "enter")
            await pilot.pause()

            self.assertEqual(len(app.query(".error-message")), 1)
            composer = app.query_one("#composer", TextArea)
            self.assertFalse(composer.disabled)
            self.assertEqual(app.focused.id, "composer")

    async def test_tool_widget_contains_only_sanitized_fields(self) -> None:
        secret = "raw-secret-image-data"

        def dispatch(value, emit=None):
            if emit is not None:
                emit(ConsoleEvent.tool("observe_screen", "running", 0.0))
                emit(ConsoleEvent.tool("observe_screen", "succeeded", 0.25))
            return _result("安全解释")

        app = create_textual_chat_app(dispatch)
        async with app.run_test() as pilot:
            await pilot.press("x", "enter")
            await pilot.pause()

            tool = app.query_one(".tool-message", Static)
            rendered = str(tool.content)
            self.assertIn("observe_screen", rendered)
            self.assertIn("succeeded", rendered)
            self.assertNotIn(secret, rendered)
            self.assertEqual(len(app.query(".tool-message")), 1)

    async def test_scrollback_shows_new_content_notice_and_resize_is_compact(
        self,
    ) -> None:
        app = create_textual_chat_app(lambda value, emit=None: _result("完成"))
        async with app.run_test(size=(100, 24)) as pilot:
            for index in range(30):
                app._append_event(
                    ConsoleEvent(ConsoleEventKind.NOTICE, f"历史消息 {index}")
                )
            await pilot.pause()
            transcript = app.query_one("#transcript", VerticalScroll)
            transcript.scroll_to(y=0, animate=False, force=True)
            await pilot.pause()
            self.assertFalse(transcript.is_vertical_scroll_end)

            app._append_event(ConsoleEvent(ConsoleEventKind.NOTICE, "新消息"))
            self.assertTrue(app.query_one("#new-content", Static).has_class("visible"))

            await pilot.resize_terminal(60, 20)
            await pilot.pause()
            self.assertTrue(app.has_class("compact"))


if __name__ == "__main__":
    unittest.main()
