"""会话持久化：JSON 文件存储与内存模型。

对外符号：
- `Session` / `SessionMessage`：会话与单条消息。
- `SessionStore`：按时间戳文件读写 `artifacts/sessions/`。
"""

from max_gui.session.store import Session, SessionMessage, SessionStore

__all__ = ["Session", "SessionMessage", "SessionStore"]
