"""不依赖具体前端的交互命令解析、展示事件与标准化操作结果。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class ConsoleEventKind(StrEnum):
    """前端允许渲染的封闭事件类别，避免依赖字符串内容推断语义。"""

    ASSISTANT = "assistant"
    COMMAND = "command"
    TOOL = "tool"
    ERROR = "error"
    NOTICE = "notice"


@dataclass(frozen=True)
class ConsoleEvent:
    """跨业务层与 UI 层传递的最小展示事件。

    工具事件只允许携带工具名、固定状态和耗时，刻意不提供任意元数据字段，
    从类型边界阻止截图、工具参数和原始回执进入对话框或后续日志。
    """

    kind: ConsoleEventKind
    text: str
    state: str | None = None
    elapsed_seconds: float | None = None

    @classmethod
    def tool(cls, tool_name: str, state: str, elapsed_seconds: float) -> ConsoleEvent:
        """创建已净化的工具状态事件，并拒绝 UI 不认识的状态。"""
        if state not in {"running", "succeeded", "failed"}:
            raise ValueError(f"不支持的工具展示状态：{state}")
        return cls(
            ConsoleEventKind.TOOL,
            tool_name,
            state=state,
            elapsed_seconds=max(0.0, elapsed_seconds),
        )


@dataclass(frozen=True)
class OperationResult:
    """前端可直接渲染的有序事件结果，并携带退出语义和进程状态码。"""

    kind: str
    events: tuple[ConsoleEvent, ...]
    should_exit: bool = False
    exit_code: int = 0


@dataclass(frozen=True)
class CommandSpec:
    """单个斜杠命令的补全、帮助和真实分发共享定义。"""

    name: str
    usage: str
    description: str


@dataclass(frozen=True)
class SessionStatus:
    """顶部状态栏和 `/status` 共用的当前会话只读快照。"""

    selected_model: str
    runtime_state: str
    safety_boundary: str = "本地 · 只读工具 · 无桌面输入 · 无网络"


COMMAND_SPECS = (
    CommandSpec("/help", "/help", "显示命令和键盘快捷键"),
    CommandSpec("/status", "/status", "显示模型、运行时和安全边界"),
    CommandSpec("/model", "/model [模型目录]", "列出或切换本地模型"),
    CommandSpec("/doctor", "/doctor", "运行本地环境诊断"),
    CommandSpec("/clear", "/clear", "清空当前本地对话历史"),
    CommandSpec("/quit", "/quit", "安全退出会话"),
)

EventSink = Callable[[ConsoleEvent], None]
DoctorHandler = Callable[[], OperationResult]
ChatHandler = Callable[[str, EventSink], str]
ModelHandler = Callable[[str | None], OperationResult]
ClearHandler = Callable[[], None]
StatusHandler = Callable[[], OperationResult]


def _ignore_event(event: ConsoleEvent) -> None:
    """为非交互调用提供无副作用事件接收器。"""


def _event(kind: ConsoleEventKind, text: str) -> tuple[ConsoleEvent, ...]:
    """简化只返回一个展示事件的命令结果构造。"""
    return (ConsoleEvent(kind, text),)


def dispatch_input(
    value: str,
    doctor: DoctorHandler | None = None,
    chat: ChatHandler | None = None,
    model: ModelHandler | None = None,
    clear: ClearHandler | None = None,
    status: StatusHandler | None = None,
    emit: EventSink | None = None,
) -> OperationResult:
    """解析聊天文本或斜杠命令，不依赖 UI 运行时并保留会话可用性。"""
    text = value.strip()
    sink = emit or _ignore_event
    if text == "/quit":
        return OperationResult(
            "quit", _event(ConsoleEventKind.NOTICE, "会话已结束。"), should_exit=True
        )
    if text == "/help":
        lines = ["支持的命令："]
        lines.extend(f"{item.usage} — {item.description}" for item in COMMAND_SPECS)
        lines.append("Enter 发送 · Shift+Enter 换行 · Ctrl+Up/Down 浏览输入历史")
        return OperationResult(
            "help", _event(ConsoleEventKind.COMMAND, "\n".join(lines))
        )
    if text == "/clear":
        if clear is not None:
            clear()
        return OperationResult(
            "clear", _event(ConsoleEventKind.NOTICE, "当前本地对话已清空。")
        )
    if text == "/status":
        if status is not None:
            return status()
        return OperationResult(
            "status",
            _event(ConsoleEventKind.COMMAND, "会话状态当前不可用。"),
        )
    if text == "/doctor":
        if doctor is None:
            return OperationResult(
                "doctor",
                _event(ConsoleEventKind.COMMAND, "Doctor 可从命令行运行。"),
            )
        return doctor()
    if text == "/model" or text.startswith("/model "):
        if model is None:
            return OperationResult(
                "model", _event(ConsoleEventKind.COMMAND, "模型选择当前不可用。")
            )
        return model(text.removeprefix("/model").strip() or None)
    if text.startswith("/"):
        return OperationResult(
            "command_error",
            _event(
                ConsoleEventKind.ERROR,
                f"不支持的命令：{text}。输入 /help 查看可用命令。",
            ),
        )
    if chat is None:
        return OperationResult(
            "runtime_error",
            _event(ConsoleEventKind.ERROR, "本地 LLM 运行时不可用。"),
        )
    try:
        return OperationResult(
            "chat",
            _event(ConsoleEventKind.ASSISTANT, chat(text, sink)),
        )
    except RuntimeError as error:
        return OperationResult(
            "runtime_error",
            _event(ConsoleEventKind.ERROR, f"本地 LLM 错误：{error}"),
        )
