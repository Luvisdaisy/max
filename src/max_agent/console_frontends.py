from __future__ import annotations

from .console_core import OperationResult


def create_textual_chat_app(dispatch):
    from textual import work
    from textual.app import App, ComposeResult
    from textual.containers import VerticalScroll
    from textual.widgets import Footer, Header, Input, Static

    class ChatApp(App[None]):
        TITLE = "MAX GUI Agent Framework"
        CSS = "#messages { height: 1fr; } Input { dock: bottom; }"

        def compose(self) -> ComposeResult:
            yield Header()
            yield VerticalScroll(
                Static(
                    "本地 Qwen3.5-2B 已就绪，可输入消息、/doctor 或 /quit。",
                    id="status",
                ),
                id="messages",
            )
            yield Input(placeholder="Message, /doctor, or /quit", id="chat-input")
            yield Footer()

        def on_input_submitted(self, event: Input.Submitted) -> None:
            value = event.value
            event.input.value = ""
            if not value.strip():
                return
            messages = self.query_one("#messages", VerticalScroll)
            messages.mount(Static(f"You: {value}"))
            if value.startswith("/"):
                self._render_result(dispatch(value))
                return
            self.query_one("#status", Static).update("正在加载或生成本地模型回复…")
            self.generate(value)

        @work(exclusive=True, thread=True)
        def generate(self, value: str) -> None:
            self.call_from_thread(self._render_result, dispatch(value))

        def _render_result(self, result: OperationResult) -> None:
            messages = self.query_one("#messages", VerticalScroll)
            for message in (
                result.messages[1:] if result.kind == "chat" else result.messages
            ):
                messages.mount(Static(message))
            self.query_one("#status", Static).update("本地会话就绪。")
            if result.should_exit:
                self.exit(result.exit_code)

    return ChatApp()


def run_textual_chat(dispatch) -> None:
    create_textual_chat_app(dispatch).run()
