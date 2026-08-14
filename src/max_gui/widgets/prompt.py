from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import TextArea


class PromptSubmitted(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class PromptInput(TextArea):
    """Enter 发送，Shift+Enter 换行。必须拦截 TextArea 默认把 Enter 当换行。"""

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(PromptSubmitted(self.text))
            return
        if event.key == "shift+enter":
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        await super()._on_key(event)
