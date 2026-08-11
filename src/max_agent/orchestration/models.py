"""受控 ReAct 运行时共享的数据契约与脱敏投影。"""

from __future__ import annotations

import hashlib
import json
import threading
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

SENSITIVE_KEYS = {
    "image",
    "screenshot",
    "text",
    "input",
    "input_text",
    "password",
    "code",
    "captcha",
    "clipboard",
    "raw",
    "model_response",
    "user_goal",
    "response_text",
    "question",
    "arguments",
    "content",
    "title",
    "value",
}


class TaskStatus(StrEnum):
    """运行时允许公开的中间态与终态。"""

    INIT = "INIT"
    REASONING = "REASONING"
    TOOL_GATE = "TOOL_GATE"
    EXECUTING_TOOL = "EXECUTING_TOOL"
    GUARDING = "GUARDING"
    ACTING = "ACTING"
    OBSERVING = "OBSERVING"
    VERIFYING = "VERIFYING"
    RECOVERING = "RECOVERING"
    APPENDING_RESULT = "APPENDING_RESULT"
    WAITING_USER = "WAITING_USER"
    CLEANING = "CLEANING"
    ARCHIVING = "ARCHIVING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"

    # 旧状态保留为输入兼容值；新图不会产生 PLANNING。
    PLANNING = "PLANNING"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AgentMessage(BaseModel):
    """任务内模型消息；完整内容仅存在于当前任务内存。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    role: MessageRole
    content: str | dict[str, Any]
    tool_name: str | None = None
    tool_call_id: str | None = None


class FinalTextResponse(BaseModel):
    """模型以纯文本结束当前受控循环。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["text"] = "text"
    text: str = Field(min_length=1)


class ToolUseResponse(BaseModel):
    """模型一轮只能提出的单个结构化工具调用。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["tool_use"] = "tool_use"
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str = Field(default_factory=lambda: str(uuid4()))
    audit_summary: str | None = Field(default=None, max_length=240)


ModelTurnResponse = FinalTextResponse | ToolUseResponse


class BudgetLimits(BaseModel):
    """所有可形成循环的能力均有独立硬上限。"""

    model_turns: int = Field(default=12, ge=1, le=64)
    tool_calls: int = Field(default=24, ge=0, le=128)
    actions: int = Field(default=12, ge=0, le=64)
    corrections: int = Field(default=1, ge=0, le=3)
    recoveries: int = Field(default=3, ge=0, le=12)
    repeated_calls: int = Field(default=2, ge=0, le=8)
    step_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    total_timeout_seconds: float = Field(default=300.0, gt=0, le=3600)


class BudgetUsage(BaseModel):
    model_turns: int = 0
    tool_calls: int = 0
    actions: int = 0
    corrections: int = 0
    recoveries: int = 0


class AgentRequest(BaseModel):
    """一次新任务或挂起任务恢复所需的前端无关输入。"""

    user_goal: str = Field(min_length=1)
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    budgets: BudgetLimits = Field(default_factory=BudgetLimits)
    cancelled: bool = False


# 兼容当前公开导入；后续调用统一使用 AgentRequest 语义。
OrchestrationRequest = AgentRequest


class WindowIdentity(BaseModel):
    """窗口授权依赖句柄、进程与真实程序路径，不依赖标题。"""

    model_config = ConfigDict(extra="forbid")

    hwnd: int = Field(gt=0)
    process_id: int = Field(gt=0)
    executable_path: str = Field(min_length=1)
    title: str = ""


class ScreenBounds(BaseModel):
    left: int
    top: int
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    def contains(self, x: int, y: int) -> bool:
        return (
            self.left <= x < self.left + self.width
            and self.top <= y < self.top + self.height
        )


class DesktopAction(BaseModel):
    """Guard 可审批的单个原子桌面动作。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "activate_window",
        "click",
        "double_click",
        "type_text",
        "scroll",
        "drag",
        "key_chord",
        "wait",
    ]
    window: WindowIdentity | None = None
    x: int | None = None
    y: int | None = None
    end_x: int | None = None
    end_y: int | None = None
    text: str | None = None
    amount: int | None = None
    keys: list[str] | None = None
    seconds: float | None = Field(default=None, ge=0, le=10)
    expected_observation: str | None = Field(default=None, max_length=240)
    high_impact: bool = False
    coordinate_space: Literal["physical", "logical", "normalized_1000"] = "physical"

    @model_validator(mode="after")
    def validate_fields(self) -> "DesktopAction":
        if self.kind in {"click", "double_click"} and (
            self.x is None or self.y is None
        ):
            raise ValueError("click actions require x and y")
        if self.kind == "drag" and None in {self.x, self.y, self.end_x, self.end_y}:
            raise ValueError("drag requires start and end coordinates")
        if self.kind == "type_text" and not self.text:
            raise ValueError("type_text requires non-empty text")
        if self.kind == "scroll" and self.amount is None:
            raise ValueError("scroll requires amount")
        if self.kind == "key_chord" and not self.keys:
            raise ValueError("key_chord requires keys")
        if self.kind == "wait" and self.seconds is None:
            raise ValueError("wait requires seconds")
        if self.kind != "type_text" and self.text is not None:
            raise ValueError("text is only valid for type_text")
        return self


class ApprovedAction(BaseModel):
    action: DesktopAction
    action_hash: str
    state_fingerprint: str
    approved_at: float
    expires_at: float
    physical_x: int | None = None
    physical_y: int | None = None


class StandardObservation(BaseModel):
    """供模型、Guard 与验证共享的标准化桌面观察。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    image_ref: Any | None = None
    captured_at: float
    bounds: ScreenBounds
    dpi: int | None = None
    foreground_window: WindowIdentity | None = None
    windows: list[dict[str, Any]] = Field(default_factory=list)
    ocr_lines: list[dict[str, Any]] = Field(default_factory=list)
    fingerprint: str
    changed_regions: list[ScreenBounds] = Field(default_factory=list)


class ToolReceiptSummary(BaseModel):
    """可安全写入审计轨迹的工具回执摘要。"""

    tool_name: str
    success: bool
    error_code: str | None = None
    message: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class StepRecord(BaseModel):
    phase: str
    receipt: ToolReceiptSummary
    audit_summary: str | None = None


class RuntimeEvent(BaseModel):
    """前端事件只含阶段、工具、状态、耗时和脱敏说明。"""

    phase: str
    state: Literal["running", "succeeded", "failed"]
    tool_name: str | None = None
    elapsed_seconds: float = Field(default=0.0, ge=0)
    message: str | None = None


class SuspendedTask(BaseModel):
    """等待用户时保留的最小状态，不含图像、坐标和批准动作。"""

    task_id: str
    user_goal_summary: str
    messages: list[AgentMessage]
    question: str
    budgets: BudgetLimits
    usage: BudgetUsage
    reasoning_mode: Literal["fast", "deliberate"] = "fast"
    confirmed_action_hash: str | None = None


class AgentResult(BaseModel):
    """运行时唯一公开结果，任何敏感工作状态均不得出现在这里。"""

    task_id: str
    status: TaskStatus
    response_text: str
    reason: str | None = None
    usage: BudgetUsage = Field(default_factory=BudgetUsage)
    receipts: list[ToolReceiptSummary] = Field(default_factory=list)
    history: list[StepRecord] = Field(default_factory=list)
    verification_evidence: list[str] = Field(default_factory=list)
    resume_token: str | None = None
    cleanup_errors: list[str] = Field(default_factory=list)

    @property
    def step_index(self) -> int:
        return self.usage.actions

    @property
    def reasoning_mode(self) -> str:
        return "deliberate" if self.usage.recoveries >= 2 else "fast"


# 兼容旧测试与外部导入名称。
OrchestrationResult = AgentResult


class CancellationToken:
    """线程安全且可注入的协作取消令牌。"""

    def __init__(self, cancelled: bool = False) -> None:
        self._event = threading.Event()
        if cancelled:
            self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


def action_hash(action: DesktopAction) -> str:
    """对规范化动作计算稳定哈希；哈希不替代 Guard 的环境复核。"""
    payload = action.model_dump(mode="json", exclude_none=True)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def summarize_data(value: Any) -> Any:
    """递归构造审计白名单投影，避免工作状态被直接序列化。"""
    if isinstance(value, BaseModel):
        return summarize_data(value.model_dump())
    if isinstance(value, dict):
        projected: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            lowered = name.lower()
            if lowered in SENSITIVE_KEYS:
                continue
            # 感知工作数据只保留计数或存在性，不能把窗口标题、OCR、
            # 资源引用或完整模型参数通过通用递归投影写入轨迹。
            if lowered == "windows":
                projected["window_count"] = len(item) if isinstance(item, list) else 0
            elif lowered in {"lines", "ocr_lines"}:
                projected["ocr_line_count"] = len(item) if isinstance(item, list) else 0
            elif lowered == "image_ref":
                projected["image_ref_present"] = item is not None
            elif lowered == "foreground_window":
                projected["foreground_window_present"] = item is not None
            elif lowered == "response" and isinstance(item, dict):
                projected[name] = {
                    field: item[field]
                    for field in ("type", "tool_name")
                    if field in item
                }
            else:
                projected[name] = summarize_data(item)
        return projected
    if isinstance(value, list):
        return [summarize_data(item) for item in value]
    if isinstance(value, tuple):
        return [summarize_data(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return f"<{type(value).__name__}>"
