"""任务终态的独立评分与可审计指标汇总。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Score:
    """成功断言的评分结果。"""

    strict_success: bool
    criteria_passed: int
    criteria_total: int

    @property
    def partial_completion_rate(self) -> float:
        """返回通过断言占全部断言的比例。"""
        return self.criteria_passed / self.criteria_total if self.criteria_total else 0.0


def score_state(state: dict[str, Any], expected: dict[str, Any]) -> Score:
    """按扁平断言比较业务状态；不依据 Agent 的最终文本评分。"""
    passed = sum(state.get(key) == value for key, value in expected.items())
    return Score(
        strict_success=passed == len(expected), criteria_passed=passed, criteria_total=len(expected)
    )
