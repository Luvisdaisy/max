"""Online-Mind2Web 的本地数据模型。

本模块只描述用户授权的任务、清单、预检和汇总，不负责网络下载或真实浏览器执行。所有记录均保持
JSON 可序列化，以便写入独立的评测目录。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse


class PreflightStatus(StrEnum):
    """一条任务在执行前或执行中得到的可审计状态。"""

    READY = "ready"
    SITE_UNREACHABLE = "site_unreachable"
    CAPTCHA_OR_LOGIN = "captcha_or_login"
    UNSAFE_ACTION_RISK = "unsafe_action_risk"
    TASK_STALE = "task_stale"
    ENVIRONMENT_ERROR = "environment_error"
    MODEL_ERROR = "model_error"
    INTERRUPTED = "interrupted"
    WEBJUDGE_ERROR = "webjudge_error"
    MODEL_INCOMPLETE = "model_incomplete"
    TRAJECTORY_VALID = "trajectory_valid"
    JUDGE_PENDING = "judge_pending"
    JUDGED = "judged"


@dataclass(frozen=True, slots=True)
class OnlineMind2WebTask:
    """一条上游 Online-Mind2Web 任务。

    参数：`task_id` 为上游裸标识；`website` 为必须直接打开的起始 URL；`instruction` 为原始英文任务；
    `reference_length` 为人工参考路径长度。
    """

    task_id: str
    website: str
    instruction: str
    reference_length: int

    def __post_init__(self) -> None:
        """拒绝不具备可安全编排条件的任务字段。"""
        parsed = urlparse(self.website)
        if not self.task_id.strip() or not self.instruction.strip() or self.reference_length <= 0:
            raise ValueError("Online-Mind2Web 任务字段不能为空，reference_length 必须为正数")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(f"任务起始网站无效：{self.website}")


@dataclass(frozen=True, slots=True)
class SafetyRule:
    """用户显式批准的一条真实网页任务边界。"""

    task_id: str
    allowed_domains: tuple[str, ...]
    max_steps: int
    timeout_seconds: int
    allowed_type_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """校验任务边界，避免空域名或非正限制被静默接受。"""
        if (
            not self.task_id
            or not self.allowed_domains
            or self.max_steps <= 0
            or self.timeout_seconds <= 0
        ):
            raise ValueError("安全清单必须包含任务、允许域名、正数步骤上限和超时")


@dataclass(frozen=True, slots=True)
class SafetyManifest:
    """一批真实网页任务的用户授权清单。"""

    name: str
    rules: tuple[SafetyRule, ...]

    def rule_for(self, task_id: str) -> SafetyRule | None:
        """返回对应任务规则；未列入即视为未授权。"""
        return next((rule for rule in self.rules if rule.task_id == task_id), None)


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """任务预检或执行终态的分类结果。"""

    task_id: str
    status: PreflightStatus
    detail: str = ""
    url: str | None = None

    @property
    def is_ready(self) -> bool:
        """仅 `ready` 允许创建真实 Agent 运行。"""
        return self.status is PreflightStatus.READY


@dataclass(frozen=True, slots=True)
class TaskMetrics:
    """单题可审计指标；未知 Token 用量保持 `None`。"""

    task_id: str
    preflight_status: PreflightStatus
    execution_status: PreflightStatus | None = None
    executed: bool = False
    duration_ms: int = 0
    tool_calls: int = 0
    total_tokens: int | None = None
    action_steps: int = 0
    reference_length: int = 0
    webjudge_label: int | None = None
    trajectory_status: PreflightStatus | None = None
    judge_status: PreflightStatus | None = None
    detail: str = ""


@dataclass(slots=True)
class EvaluationSummary:
    """批次汇总并提供 JSON 可写出的稳定字段。"""

    planned_tasks: int
    results: list[TaskMetrics] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """按模型、环境和安全分母分离的口径导出汇总。"""
        ready = [item for item in self.results if item.preflight_status is PreflightStatus.READY]
        executed = [item for item in ready if item.executed]
        judged = [item for item in executed if item.webjudge_label is not None]
        model_incomplete = [
            item for item in executed if item.execution_status is PreflightStatus.MODEL_INCOMPLETE
        ]
        trajectories = [
            item for item in executed if item.trajectory_status is PreflightStatus.TRAJECTORY_VALID
        ]
        judge_pending = [
            item for item in trajectories if item.judge_status is PreflightStatus.JUDGE_PENDING
        ]
        judge_errors = [
            item for item in trajectories if item.judge_status is PreflightStatus.WEBJUDGE_ERROR
        ]
        environment = [
            item
            for item in self.results
            if item.preflight_status
            in {
                PreflightStatus.SITE_UNREACHABLE,
                PreflightStatus.CAPTCHA_OR_LOGIN,
                PreflightStatus.TASK_STALE,
                PreflightStatus.ENVIRONMENT_ERROR,
            }
            or item.execution_status
            in {
                PreflightStatus.SITE_UNREACHABLE,
                PreflightStatus.CAPTCHA_OR_LOGIN,
                PreflightStatus.TASK_STALE,
                PreflightStatus.ENVIRONMENT_ERROR,
            }
        ]
        blocked = [
            item
            for item in self.results
            if item.preflight_status is PreflightStatus.UNSAFE_ACTION_RISK
            or item.execution_status is PreflightStatus.UNSAFE_ACTION_RISK
        ]
        success = sum(item.webjudge_label == 1 for item in judged)
        known_tokens = [item.total_tokens for item in executed if item.total_tokens is not None]
        return {
            "planned_tasks": self.planned_tasks,
            "ready_tasks": len(ready),
            "executed_tasks": len(executed),
            "environment_unexecutable_tasks": len(environment),
            "safety_blocked_tasks": len(blocked),
            "webjudge_evaluated_tasks": len(judged),
            "model_incomplete_tasks": len(model_incomplete),
            "trajectory_valid_tasks": len(trajectories),
            "judge_pending_tasks": len(judge_pending),
            "judge_error_tasks": len(judge_errors),
            "model_completion_rate": len(trajectories) / len(executed) if executed else None,
            "model_task_success_rate": success / len(judged) if judged else None,
            "end_to_end_success_rate": success / self.planned_tasks if judged else None,
            "known_token_samples": len(known_tokens),
            "total_tokens": sum(known_tokens) if known_tokens else None,
            "average_action_efficiency": (
                sum(
                    item.action_steps / item.reference_length
                    for item in executed
                    if item.reference_length
                )
                / len([item for item in executed if item.reference_length])
                if any(item.reference_length for item in executed)
                else None
            ),
            "results": [asdict(item) for item in self.results],
        }
