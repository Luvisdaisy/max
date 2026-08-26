"""从助手文本解析编号计划，并按规则推进当前子任务。"""

from __future__ import annotations

import re

_PLAN_LINE = re.compile(r"^\s*\d+[\.、\)]\s+(.+?)\s*$")


def extract_numbered_plan(text: str) -> list[str]:
    """抽出至少两行的编号子任务；不足两行返回空列表。

    参数：
        text: 助手文本。

    返回：
        子任务文案列表。
    """
    items: list[str] = []
    for line in text.splitlines():
        matched = _PLAN_LINE.match(line)
        if matched:
            body = matched.group(1).strip()
            if body:
                items.append(body)
    return items if len(items) >= 2 else []


def ingest_assistant_plan(
    text: str, plan: list[str], current_subtask: str | None
) -> tuple[list[str], str | None]:
    """助手文本若含编号列表则覆盖计划，否则保持原值。

    参数：
        text: 本轮助手文本。
        plan: 已有计划。
        current_subtask: 已有当前子任务。

    返回：
        `(plan, current_subtask)`。
    """
    numbered = extract_numbered_plan(text)
    if numbered:
        return numbered, numbered[0]
    return list(plan), current_subtask


def advance_subtask_after_tools(
    *,
    plan: list[str],
    current_subtask: str | None,
    assistant_text: str,
    tool_failed: bool,
) -> tuple[list[str], str | None]:
    """工具失败则不推进；成功且助手写了完成/下一则前进一项。

    参数：
        plan: 当前计划。
        current_subtask: 当前子任务。
        assistant_text: 产生这些工具调用的助手文本。
        tool_failed: 本轮是否有工具失败或取消。

    返回：
        更新后的 `(plan, current_subtask)`。
    """
    plan = list(plan)
    if tool_failed or not plan:
        return plan, current_subtask

    # 支持结构化 JSON 输出中的 status 和 reason
    if "status" in assistant_text and "error" in assistant_text.lower():
        return plan, current_subtask

    if "子任务完成" not in assistant_text and "下一子任务" not in assistant_text:
        return plan, current_subtask

    if current_subtask in plan:
        index = plan.index(current_subtask)
    else:
        index = 0
    index = min(index + 1, len(plan) - 1)
    return plan, plan[index]
