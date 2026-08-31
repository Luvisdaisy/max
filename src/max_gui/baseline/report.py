"""基线评测运行记录的原子写入与批次指标聚合。"""

from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from max_gui.baseline.models import BaselineResult, BaselineStatus
from max_gui.baseline.scoring import SCORE_VERSION


def write_run_record(path: Path, manifest: dict[str, Any], results: list[BaselineResult]) -> None:
    """原子写入一份包含评分的基线运行 JSON。

    参数：`path` 是最终记录路径，`manifest` 是运行参数，`results` 是逐题结果。
    返回：无。
    异常：目录不可写或原子替换失败时传播文件系统异常。
    """
    payload = {
        "manifest": manifest,
        "summary": summarize(results),
        "results": [item.to_dict() for item in results],
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(_dump(payload), encoding="utf-8")
    os.replace(temporary, path)


def summarize(results: list[BaselineResult]) -> dict[str, Any]:
    """聚合跨轮指标、评分覆盖率和完整批次总分。

    参数：`results` 是本次运行的全部逐题结果。
    返回：保留未知值 `None` 语义的 JSON 友好字典。
    """
    measured = [item for item in results if item.preflight_status is BaselineStatus.READY]
    known_exec = [item.execution_tokens for item in measured if item.execution_tokens is not None]
    known_review = [item.review_tokens for item in measured if item.review_tokens is not None]
    scores = [item.score.total for item in results if item.score and item.score.total is not None]
    by_task: dict[str, list[BaselineResult]] = defaultdict(list)
    for item in results:
        by_task[item.task_id].append(item)
    return {
        "tasks": len(results),
        "measured_tasks": len(measured),
        "environment_blocked": sum(
            item.preflight_status is BaselineStatus.ENVIRONMENT_BLOCKED for item in results
        ),
        "safety_blocked": sum(
            item.preflight_status is BaselineStatus.SAFETY_BLOCKED for item in results
        ),
        "success_rate": (
            sum(item.success for item in measured) / len(measured) if measured else None
        ),
        "average_actions": _mean([item.actions for item in measured]),
        "average_execution_duration_ms": _mean([item.execution_duration_ms for item in measured]),
        "average_total_duration_ms": _mean([item.total_duration_ms for item in measured]),
        "total_model_calls": _complete_sum([item.model_calls for item in measured]),
        "total_tool_calls": _complete_sum([item.tool_calls for item in measured]),
        "total_tool_failures": _complete_sum([item.tool_failures for item in measured]),
        "known_execution_token_samples": len(known_exec),
        "known_execution_tokens": _complete_sum([item.execution_tokens for item in measured]),
        "known_review_token_samples": len(known_review),
        "known_review_tokens": sum(known_review) if known_review else None,
        "review_errors": sum(item.review_error is not None for item in measured),
        "review_indeterminate": sum(
            item.review_verdict is not None and item.review_verdict.value == "indeterminate"
            for item in measured
        ),
        "review_passes": sum(
            item.review_verdict is not None and item.review_verdict.value == "pass"
            for item in measured
        ),
        "termination_reasons": dict(Counter(str(item.execution_status) for item in measured)),
        "overall_score": (
            round(sum(scores) / len(scores), 2) if results and len(scores) == len(results) else None
        ),
        "score_coverage": len(scores) / len(results) if results else 0.0,
        "score_version": SCORE_VERSION,
        "by_task": {
            name: {
                "n": len(items),
                "success_rate": sum(item.success for item in items) / len(items),
                "average_execution_duration_ms": _mean(
                    [item.execution_duration_ms for item in items]
                ),
                "average_actions": _mean([item.actions for item in items]),
                "review_verdicts": dict(Counter(str(item.review_verdict) for item in items)),
            }
            for name, items in by_task.items()
        },
        "results": [item.to_dict() for item in results],
    }


def _mean(values: list[int | None]) -> float | None:
    """只对已知数值计算均值；完全未知时返回空值。"""
    known = [value for value in values if value is not None]
    return sum(known) / len(known) if known else None


def _complete_sum(values: list[int | None]) -> int | None:
    """仅在全部样本已知时求和，避免把缺失样本静默忽略。"""
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _dump(value: object) -> str:
    """生成带结尾换行的 UTF-8 JSON。"""
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"
