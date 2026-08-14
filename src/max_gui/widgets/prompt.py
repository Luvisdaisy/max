"""REPL 多行输入框：Enter 发送，Shift+Enter 换行。"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import TextArea


class PromptSubmitted(Message):
    """用户按 Enter 提交当前文本。"""

    def __init__(self, text: str) -> None:
        """参数：`text` 为输入框当前全部内容，可含换行。"""
        super().__init__()
        self.text = text


class PromptInput(TextArea):
    """Enter 发送，Shift+Enter 换行。必须拦截 TextArea 默认把 Enter 当换行。"""

    async def _on_key(self, event: events.Key) -> None:
        """拦截 Enter / Shift+Enter；其余按键交给 TextArea。

        参数：
            event: Textual 按键事件。
        """
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
