"""编排器输入、步骤记录和结果的显式数据模型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    """任务状态机允许的终态与中间态。"""

    INIT = "INIT"
    OBSERVING = "OBSERVING"
    PLANNING = "PLANNING"
    GUARDING = "GUARDING"
    ACTING = "ACTING"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    WAITING_USER = "WAITING_USER"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class OrchestrationRequest(BaseModel):
    """一次编排请求的目标、模式、可用工具和初始上下文。"""

    user_goal: str = Field(min_length=1)
    max_steps: int = Field(default=12, ge=1, le=12)
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    cancelled: bool = False


class ToolReceiptSummary(BaseModel):
    """可安全写入步骤记录的工具回执摘要。"""

    tool_name: str
    success: bool
    error_code: str | None = None
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class StepRecord(BaseModel):
    """一个状态机阶段的执行记录，供验证和审计使用。"""

    phase: str
    receipt: ToolReceiptSummary


class OrchestrationResult(BaseModel):
    """编排完成后的状态、步骤与面向用户的结果信息。"""

    task_id: str
    status: TaskStatus
    step_index: int
    reason: str | None = None
    reasoning_mode: str
    receipts: list[ToolReceiptSummary]
    history: list[StepRecord]
    verification_evidence: list[str]


def summarize_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: summarize_data(item)
            for key, item in value.items()
            if key not in {"image", "screenshot", "text", "input", "password"}
        }
    if isinstance(value, list):
        return [summarize_data(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return f"<{type(value).__name__}>"
