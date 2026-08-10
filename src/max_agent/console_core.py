"""不依赖具体前端的交互命令解析与标准化操作结果。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationResult:
    """前端可直接渲染的操作结果，并携带退出语义和进程状态码。"""

    kind: str
    messages: tuple[str, ...]
    should_exit: bool = False
    exit_code: int = 0


DoctorHandler = Callable[[], OperationResult]
ChatHandler = Callable[[str], str]
ModelHandler = Callable[[str | None], OperationResult]


def dispatch_input(
    value: str,
    doctor: DoctorHandler | None = None,
    chat: ChatHandler | None = None,
    model: ModelHandler | None = None,
) -> OperationResult:
    """解析聊天文本或斜杠命令，不依赖 UI 运行时并保留会话可用性。"""
    text = value.strip()
    if text == "/quit":
        return OperationResult("quit", ("Session ended.",), should_exit=True)
    if text == "/doctor":
        if doctor is None:
            return OperationResult(
                "doctor", ("Doctor is available from the command line.",)
            )
        return doctor()
    if text == "/model" or text.startswith("/model "):
        if model is None:
            return OperationResult("model", ("模型选择当前不可用。",))
        return model(text.removeprefix("/model").strip() or None)
    if text.startswith("/"):
        return OperationResult("command_error", (f"Unsupported command: {text}",))
    if chat is None:
        return OperationResult("chat", (text, "本地 LLM 运行时不可用。"))
    try:
        return OperationResult("chat", (text, chat(text)))
    except RuntimeError as error:
        return OperationResult("runtime_error", (f"本地 LLM 错误：{error}",))
