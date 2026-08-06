from __future__ import annotations

from collections.abc import Callable

from .console_core import OperationResult


Dispatch = Callable[[str], OperationResult]
Render = Callable[[str], None]


def run_line_console(*, read_line: Callable[[], str], dispatch: Dispatch, render: Render) -> None:
    """Run a UI-neutral line loop, enabling deterministic fallback tests."""
    while True:
        result = dispatch(read_line())
        for message in result.messages:
            render(message)
        if result.should_exit:
            return


def run_prompt_toolkit_console(dispatch: Dispatch) -> None:
    from prompt_toolkit import PromptSession
    from rich.console import Console

    console = Console()
    session = PromptSession("MAX > ")
    try:
        run_line_console(read_line=session.prompt, dispatch=dispatch, render=console.print)
    except (EOFError, KeyboardInterrupt):
        console.print("Session ended.")


def run_textual_chat(dispatch: Dispatch) -> None:
    from textual.app import App, ComposeResult
    from textual.containers import VerticalScroll
    from textual.widgets import Footer, Header, Input, Static

    class ChatApp(App[None]):
        TITLE = "MAX GUI Agent Framework"
        CSS = "#messages { height: 1fr; } Input { dock: bottom; }"

        def compose(self) -> ComposeResult:
            yield Header()
            yield VerticalScroll(Static("AI backend is not configured. Use /diagnose or /quit.", id="status"), id="messages")
            yield Input(placeholder="Message, /diagnose, or /quit", id="chat-input")
            yield Footer()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            value = event.value
            event.input.value = ""
            messages = self.query_one("#messages", VerticalScroll)
            result = dispatch(value)
            for message in result.messages:
                messages.mount(Static(message))
            if result.should_exit:
                self.exit(result.exit_code)

    ChatApp().run()
