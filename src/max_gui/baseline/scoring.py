"""基线任务的版本化纯评分算法，不读取文件或调用模型。"""

from __future__ import annotations

from max_gui.baseline.models import (
    BaselineScore,
    BaselineScoreReferences,
    BaselineStatus,
    ReviewVerdict,
)

SCORE_VERSION = "baseline-score-v2"


def calculate_score(
    *,
    timeout_seconds: int,
    preflight_status: BaselineStatus,
    review_verdict: ReviewVerdict | None,
    review_error: str | None,
    has_screenshot: bool,
    execution_duration_ms: int | None,
    actions: int | None,
    tool_calls: int | None,
    tool_failures: int | None,
    execution_tokens: int | None,
) -> BaselineScore:
    """按 `baseline-score-v2` 计算单题总分及六个分项。

    参数：各字段均来自同一单题结果；`timeout_seconds` 来自任务契约。
    返回：包含固定参考值和完整性的不可变评分。
    异常：超时配置非正或任一已知计数为负时抛出 `ValueError`。
    """
    if timeout_seconds <= 0:
        raise ValueError("评分超时必须为正数")
    values = {
        "execution_duration_ms": execution_duration_ms,
        "actions": actions,
        "tool_calls": tool_calls,
        "tool_failures": tool_failures,
        "execution_tokens": execution_tokens,
    }
    if any(value is not None and value < 0 for value in values.values()):
        raise ValueError("评分指标不得为负数")

    references = BaselineScoreReferences(timeout_ms=timeout_seconds * 1000)
    if preflight_status is not BaselineStatus.READY:
        return BaselineScore(
            SCORE_VERSION,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            ("not_measured",),
            references,
        )

    effect = _effect_score(review_verdict, review_error, has_screenshot)
    execution_time = _inverse_score(execution_duration_ms, references.timeout_ms, 10.0)
    action_score = _inverse_score(actions, references.actions, 5.0)
    tool_call_score = _inverse_score(tool_calls, references.tool_calls, 5.0)
    reliability = _reliability_score(tool_calls, tool_failures)
    token_score = _inverse_score(execution_tokens, references.execution_tokens, 5.0)
    components = {
        "execution_duration_ms": execution_time,
        "actions": action_score,
        "tool_calls": tool_call_score,
        "tool_reliability": reliability,
        "execution_tokens": token_score,
    }
    missing = tuple(name for name, value in components.items() if value is None)
    complete = not missing
    total = None
    if complete:
        total = round(
            effect + execution_time + action_score + tool_call_score + reliability + token_score,
            2,
        )
    return BaselineScore(
        SCORE_VERSION,
        total,
        effect,
        execution_time,
        action_score,
        tool_call_score,
        reliability,
        token_score,
        complete,
        missing,
        references,
    )


def _effect_score(
    verdict: ReviewVerdict | None,
    review_error: str | None,
    has_screenshot: bool,
) -> float:
    """把独立评审结论映射为固定的 70 分效果项。"""
    if not has_screenshot or review_error or verdict is ReviewVerdict.FAIL:
        return 0.0
    if verdict is ReviewVerdict.PASS:
        return 70.0
    if verdict is ReviewVerdict.INDETERMINATE:
        return 35.0
    return 0.0


def _inverse_score(value: int | None, reference: int, weight: float) -> float | None:
    """按固定上限计算越小越优的线性分项，并裁剪到有效范围。"""
    if value is None:
        return None
    return round(weight * _clamp(1 - value / reference), 4)


def _reliability_score(tool_calls: int | None, tool_failures: int | None) -> float | None:
    """按工具失败占比计算可靠性分项；零调用按分母一处理。"""
    if tool_calls is None or tool_failures is None:
        return None
    return round(5.0 * _clamp(1 - tool_failures / max(tool_calls, 1)), 4)


def _clamp(value: float) -> float:
    """把浮点数限制在闭区间 0–1。"""
    return max(0.0, min(1.0, value))
