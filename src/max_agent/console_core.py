from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationResult:
    kind: str
    messages: tuple[str, ...]
    should_exit: bool = False
    exit_code: int = 0


DiagnoseHandler = Callable[[], OperationResult]


def dispatch_input(value: str, diagnose: DiagnoseHandler | None = None) -> OperationResult:
    """Translate a chat line or slash command without depending on a UI runtime."""
    text = value.strip()
    if text == "/quit":
        return OperationResult("quit", ("Session ended.",), should_exit=True)
    if text == "/diagnose":
        if diagnose is None:
            return OperationResult("diagnose", ("Diagnostics are available from the command line.",))
        return diagnose()
    if text.startswith("/"):
        return OperationResult("command_error", (f"Unsupported command: {text}",))
    return OperationResult("chat", (text, "AI backend is not configured. No model response was generated."))
