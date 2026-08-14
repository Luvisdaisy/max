"""Textual 控件：多行提示框与提交消息。

对外符号：
- `PromptInput`：Enter 发送、Shift+Enter 换行。
- `PromptSubmitted`：提交时携带输入文本。
"""

from max_gui.widgets.prompt import PromptInput, PromptSubmitted

__all__ = ["PromptInput", "PromptSubmitted"]
