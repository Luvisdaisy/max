"""任务结果、终止原因与 JSON/Markdown 报告。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

TerminationReason = Literal[
    "completed",
    "timeout",
    "tool_limit",
    "violation",
    "agent_error",
    "interrupted",
    "environment_error",
]


@dataclass(frozen=True, slots=True)
class TaskResult:
    """单题不可变结果，未知 Token 用量保持 None。"""

    task_id: str
    suite_version: str
    model: str
    strict_success: bool
    criteria_passed: int
    criteria_total: int
    termination_reason: TerminationReason
    duration_ms: int
    tool_calls: int
    tool_failures: int
    invalid_actions: int
    violations: tuple[str, ...]
    total_tokens: int | None


def termination_reason(
    *,
    agent_status: str,
    tool_calls: int,
    limit: int,
    violations: list[str],
    timed_out: bool,
    environment_error: bool = False,
) -> TerminationReason:
    """按优先级把运行状态归一为可区分终止原因。"""
    if environment_error:
        return "environment_error"
    if violations:
        return "violation"
    if timed_out:
        return "timeout"
    if tool_calls > limit:
        return "tool_limit"
    if agent_status == "interrupted":
        return "interrupted"
    if agent_status == "error":
        return "agent_error"
    return "completed"


def write_report(
    results: list[TaskResult], path: Path, *, requested_tasks: int
) -> dict[str, object]:
    """写入逐题 JSON 和同路径 Markdown 汇总，保留计划评测规模。

    参数：`results` 为已结束任务的结果；`path` 为 JSON 输出路径；`requested_tasks` 为首页选择的
        10 或 100 条批次规模。
    返回：写入文件的汇总字典。
    异常：目录创建或文件写入失败时透传 `OSError`。
    """
    measured = [item for item in results if item.termination_reason != "environment_error"]
    total = len(measured)
    summary = {
        "requested_tasks": requested_tasks,
        "tasks": len(results),
        "measured_tasks": total,
        "task_success_rate": sum(item.strict_success for item in measured) / total
        if total
        else 0.0,
        "partial_completion_rate": sum(
            item.criteria_passed / item.criteria_total for item in measured if item.criteria_total
        )
        / total
        if total
        else 0.0,
        "average_duration_ms": sum(item.duration_ms for item in measured) / total if total else 0.0,
        "average_tool_calls": sum(item.tool_calls for item in measured) / total if total else 0.0,
        "tool_failure_rate": sum(item.tool_failures for item in measured)
        / sum(item.tool_calls for item in measured)
        if sum(item.tool_calls for item in measured)
        else 0.0,
        "invalid_action_rate": sum(item.invalid_actions for item in measured)
        / sum(item.tool_calls for item in measured)
        if sum(item.tool_calls for item in measured)
        else 0.0,
        "violation_rate": sum(bool(item.violations) for item in measured) / total if total else 0.0,
        "known_token_samples": sum(item.total_tokens is not None for item in results),
        "total_tokens": sum(item.total_tokens or 0 for item in results),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"summary": summary, "results": [asdict(item) for item in results]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    path.with_suffix(".md").write_text(
        "# GUI Agent 评测报告\n\n"
        + "\n".join(f"- {key}: {value}" for key, value in summary.items())
        + "\n",
        encoding="utf-8",
    )
    return summary
