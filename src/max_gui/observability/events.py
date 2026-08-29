"""运行事件值对象：稳定信封、编号生成与安全异常摘要。

事件只保存运行诊断所需的小字段。reasoning、键盘输入、OCR 全文与图像字节由
会话或资源文件持有，不得复制进这里的 `data`。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

RunEventType = Literal[
    "run.started",
    "run.resumed",
    "run.completed",
    "run.failed",
    "run.interrupted",
    "state.changed",
    "model.started",
    "model.retrying",
    "model.completed",
    "model.failed",
    "tool.started",
    "tool.completed",
    "tool.failed",
    "observation.completed",
    "recorder.failed",
]

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|token)\s*[:=]\s*)[^\s,;]+"),
)
_MAX_ERROR_CHARS = 500


def new_run_id() -> str:
    """生成带本地时间前缀和随机后缀的运行编号。

    返回：
        形如 `run-20260821-153012-1a2b3c4d` 的本机唯一编号。
    """
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return f"run-{stamp}-{uuid4().hex[:8]}"


def safe_error_summary(error: BaseException | str) -> str:
    """把异常收成短诊断，并遮蔽常见 Authorization、API Key 与 token。

    参数：
        error: 捕获到的异常或现成错误文本。

    返回：
        最多 500 字符的安全摘要；异常输入带异常类型。
    """
    if isinstance(error, BaseException):
        text = f"{type(error).__name__}: {error}"
    else:
        text = str(error)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1***", text)
    return text[:_MAX_ERROR_CHARS]


@dataclass(frozen=True, slots=True)
class RunEvent:
    """一次运行中的结构化事件。

    字段：
        schema_version: 信封版本，第一版固定为 1。
        event_id: `run_id:sequence` 形式的稳定定位符。
        sequence: 同一运行内从 1 开始严格递增的顺序号。
        timestamp: 带本地时区、毫秒精度的 ISO 时间。
        elapsed_ms: 从当前记录器启动或恢复起计算的单调耗时。
        run_id: 单次用户任务编号。
        session_id: 长期会话编号。
        event_type: 有限事件类型。
        iteration: 当前 ReAct 轮次。
        subtask: 当前轻量计划子任务。
        data: 不含大段敏感正文的事件载荷。
    """

    event_id: str
    sequence: int
    timestamp: str
    elapsed_ms: int
    run_id: str
    session_id: str
    event_type: RunEventType
    iteration: int
    subtask: str | None
    data: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """返回可直接编码为 JSON 的普通字典。"""
        return asdict(self)
