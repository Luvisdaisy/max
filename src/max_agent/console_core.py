from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationResult:
    kind: str
    messages: tuple[str, ...]
    should_exit: bool = False
    exit_code: int = 0


DoctorHandler = Callable[[], OperationResult]
ChatHandler = Callable[[str], str]


def dispatch_input(
    value: str, doctor: DoctorHandler | None = None, chat: ChatHandler | None = None
) -> OperationResult:
    """Translate a chat line or slash command without depending on a UI runtime."""
    text = value.strip()
    if text == "/quit":
        return OperationResult("quit", ("Session ended.",), should_exit=True)
    if text == "/doctor":
        if doctor is None:
            return OperationResult(
                "doctor", ("Doctor is available from the command line.",)
            )
        return doctor()
    if text.startswith("/"):
        return OperationResult("command_error", (f"Unsupported command: {text}",))
    if chat is None:
        return OperationResult("chat", (text, "本地 LLM 运行时不可用。"))
    try:
        return OperationResult("chat", (text, chat(text)))
    except RuntimeError as error:
        return OperationResult("runtime_error", (f"本地 LLM 错误：{error}",))
