"""计划解析：编号列表、改计划与工具失败不推进。"""

from __future__ import annotations

from max_gui.agent.plan import (
    advance_subtask_after_tools,
    extract_numbered_plan,
    ingest_assistant_plan,
)


def test_extract_requires_two_items() -> None:
    """单行编号不算计划；两行才收下。"""
    assert extract_numbered_plan("1. 只有一项") == []
    assert extract_numbered_plan("1. 打开计算器\n2. 输入 1+1") == ["打开计算器", "输入 1+1"]


def test_ingest_overwrites_plan() -> None:
    """新的编号列表覆盖旧计划。"""
    plan, current = ingest_assistant_plan(
        "改计划\n1. 先截图\n2. 再点击",
        ["旧任务"],
        "旧任务",
    )
    assert plan == ["先截图", "再点击"]
    assert current == "先截图"


def test_advance_skips_when_tool_failed() -> None:
    """工具失败时即使写了子任务完成也不推进。"""
    plan, current = advance_subtask_after_tools(
        plan=["打开计算器", "输入 1+1"],
        current_subtask="打开计算器",
        assistant_text="子任务完成",
        tool_failed=True,
    )
    assert current == "打开计算器"
    assert plan[0] == "打开计算器"


def test_advance_moves_to_next_item() -> None:
    """成功后推进到下一项，末项不再越界。"""
    plan, current = advance_subtask_after_tools(
        plan=["A", "B"],
        current_subtask="A",
        assistant_text="下一子任务",
        tool_failed=False,
    )
    assert current == "B"
    _, last = advance_subtask_after_tools(
        plan=plan,
        current_subtask="B",
        assistant_text="子任务完成",
        tool_failed=False,
    )
    assert last == "B"
