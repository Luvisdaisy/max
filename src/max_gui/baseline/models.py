"""基线桌面评测的版本化任务与结果数据模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
    """任务副作用分级。"""

    READ_ONLY = "read_only"
    PERSONAL_WRITE = "personal_write"


class BaselineStatus(StrEnum):
    """预检、执行和评审共用的稳定终态。"""

    READY = "ready"
    ENVIRONMENT_BLOCKED = "environment_blocked"
    SAFETY_BLOCKED = "safety_blocked"
    TIMEOUT = "timeout"
    TOOL_LIMIT = "tool_limit"
    VIOLATION = "violation"
    AGENT_ERROR = "agent_error"
    AGENT_INCOMPLETE = "agent_incomplete"
    REVIEW_ERROR = "review_error"
    TIMEOUT_FORCED = "timeout_forced"
    COMPLETED = "completed"


class ReviewVerdict(StrEnum):
    """独立截图评审的三值结论。"""

    PASS = "pass"
    FAIL = "fail"
    INDETERMINATE = "indeterminate"


@dataclass(frozen=True, slots=True)
class BaselineTask:
    """一条真实桌面任务的不可变契约。"""

    id: str
    prompt: str
    review_rubric: str
    preconditions: tuple[str, ...]
    risk: RiskLevel
    timeout_seconds: int
    nonce_template: str | None = None

    def render_prompt(self, nonce: str, run_date: str) -> str:
        """替换任务提示词中的受控 nonce 与运行日期占位符。"""
        return self.prompt.replace("{nonce}", nonce).replace("{run_date}", run_date)

    def render_rubric(self, nonce: str, run_date: str) -> str:
        """替换评审规则中的受控 nonce 与运行日期占位符。"""
        return self.review_rubric.replace("{nonce}", nonce).replace("{run_date}", run_date)


@dataclass(frozen=True, slots=True)
class ReviewResult:
    """截图评审的最小结构化结果。"""

    verdict: ReviewVerdict | None
    visible_evidence: str
    reason: str
    duration_ms: int
    total_tokens: int | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class BaselineResult:
    """单题单轮的审计指标；未知数值固定为 `None`。"""

    task_id: str
    round_id: str
    nonce: str
    prompt_version: str
    preflight_status: BaselineStatus
    execution_status: BaselineStatus | None
    review_verdict: ReviewVerdict | None
    review_error: str | None
    agent_claimed_complete: bool
    success: bool
    execution_duration_ms: int | None
    review_duration_ms: int | None
    total_duration_ms: int
    tool_calls: int | None
    tool_failures: int | None
    actions: int | None
    violations: tuple[str, ...]
    execution_tokens: int | None
    review_tokens: int | None
    final_screenshot: str | None
    screenshot_source: str | None
    run_log: str | None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为 JSON 友好的普通字典。"""
        return asdict(self)
