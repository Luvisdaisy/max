"""所有工具共享的权限、上下文、失败表示和调用协议。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from max_agent.orchestration.models import CancellationToken, RuntimeEvent
from max_agent.orchestration.resources import InMemoryResourceStore


class ToolFailureCode(StrEnum):
    """工具调用失败的稳定分类，底层异常不得成为协议。"""

    INVALID_INPUT = "invalid_input"
    UNKNOWN_TOOL = "unknown_tool"
    UNAVAILABLE = "unavailable"
    EXECUTION_FAILED = "execution_failed"
    PHASE_DENIED = "phase_denied"
    PERMISSION_DENIED = "permission_denied"
    POLICY_DENIED = "policy_denied"
    BUDGET_EXHAUSTED = "budget_exhausted"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    STALE_TARGET = "stale_target"


class ToolPermission(StrEnum):
    OBSERVE = "observe"
    MODEL = "model"
    GUARD = "guard"
    CONTROL = "control"
    VERIFY = "verify"
    RECOVER = "recover"
    ARCHIVE = "archive"
    USER = "user"


class ToolPhase(StrEnum):
    REASON = "reason"
    TOOL = "tool"
    GUARD = "guard"
    ACTION = "action"
    OBSERVE_AFTER_ACTION = "observe_after_action"
    VERIFY = "verify"
    RECOVER = "recover"
    ARCHIVE = "archive"


class ToolError(BaseModel):
    code: ToolFailureCode
    message: str


class ToolReceipt(BaseModel):
    """工具结构化回执；任务工作数据和审计投影由运行时分别处理。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tool_name: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: ToolError | None = None

    @classmethod
    def failure(
        cls, tool_name: str, code: ToolFailureCode, message: str
    ) -> "ToolReceipt":
        return cls(
            tool_name=tool_name,
            success=False,
            error=ToolError(code=code, message=message),
        )


@dataclass(frozen=True, slots=True)
class ToolContext:
    """工具只读调用上下文，不允许工具直接修改全局图状态。"""

    task_id: str
    phase: ToolPhase
    resources: InMemoryResourceStore
    cancellation: CancellationToken
    consume_budget: Callable[[str], bool]
    emit: Callable[[RuntimeEvent], None] | None = None


class Tool(Protocol):
    """注册表可调用工具的完整契约。"""

    name: str
    description: str
    input_model: type[BaseModel]
    permission: ToolPermission
    allowed_phases: frozenset[ToolPhase]
    timeout_seconds: float
    recoverable: bool
    model_visible: bool
    side_effect: bool

    def invoke(
        self, tool_input: BaseModel, context: ToolContext | None = None
    ) -> ToolReceipt: ...
