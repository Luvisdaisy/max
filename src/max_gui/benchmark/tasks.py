"""版本化 Web GUI 任务的加载与校验。

任务文件是评测的唯一公开输入；评分断言仅由评测运行器读取，不能渲染到 Agent 可见页面。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SUITE = PROJECT_ROOT / "artifacts" / "benchmarks" / "web-gui-v1.json"
REQUIRED_CATEGORIES = {"basic", "single_page", "multi_step", "robustness"}
SMOKE_DIFFICULTY_QUOTAS = {"easy": 4, "medium": 3, "hard": 3}


@dataclass(frozen=True, slots=True)
class BenchmarkTask:
    """一条可重置、可独立判分的 GUI 评测任务。"""

    id: str
    route: str
    instruction: str
    initial_state: dict[str, Any]
    success: dict[str, Any]
    forbidden_actions: tuple[str, ...]
    max_tool_calls: int
    timeout_seconds: int
    category: str
    difficulty: str


@dataclass(frozen=True, slots=True)
class TaskSuite:
    """带版本号的任务集合。"""

    version: str
    tasks: tuple[BenchmarkTask, ...]


def load_task_suite(path: Path = DEFAULT_SUITE) -> TaskSuite:
    """读取并严格校验任务集。

    参数：path 为 JSON 文件。返回版本化任务集；字段缺失、类别不全或标识重复时抛出 ValueError。
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("version"), str):
        raise ValueError("任务集必须含字符串 version")
    entries = raw.get("tasks")
    if not isinstance(entries, list) or len(entries) < 20:
        raise ValueError("任务模板必须至少包含 20 条")
    copies = int(raw.get("copies_per_template") or 1)
    if copies <= 0:
        raise ValueError("copies_per_template 必须为正数")
    templates = tuple(_task_from_dict(item) for item in entries)
    tasks = tuple(
        replace(task, id=f"{task.id}-v{copy}")
        for copy in range(1, copies + 1)
        for task in templates
    )
    ids = [task.id for task in tasks]
    if len(tasks) < 100:
        raise ValueError("任务集展开后必须至少包含 100 条任务")
    if len(set(ids)) != len(ids):
        raise ValueError("任务标识不得重复")
    categories = {task.category for task in tasks}
    if not REQUIRED_CATEGORIES.issubset(categories):
        raise ValueError("任务集必须覆盖四类任务")
    return TaskSuite(version=raw["version"], tasks=tasks)


def select_task_batch(suite: TaskSuite, task_count: int) -> tuple[BenchmarkTask, ...]:
    """从已校验任务集选择固定规模的可复现批次。

    参数：`suite` 为完整版本化任务集；`task_count` 仅支持 10 或 100。
    返回：100 时返回完整任务序列；10 时返回按原始顺序排列的 4 easy、3 medium、3 hard 任务。
    异常：任务数量不受支持，或任务集不能满足难度配额时抛出 `ValueError`。
    """
    if task_count == 100:
        return suite.tasks
    if task_count != 10:
        raise ValueError("任务数量仅支持 10 或 100")
    remaining = dict(SMOKE_DIFFICULTY_QUOTAS)
    selected: list[BenchmarkTask] = []
    for task in suite.tasks:
        if remaining.get(task.difficulty, 0) <= 0:
            continue
        selected.append(task)
        remaining[task.difficulty] -= 1
    if any(remaining.values()):
        missing = ", ".join(name for name, count in remaining.items() if count)
        raise ValueError(f"任务集缺少冒烟评测所需难度：{missing}")
    return tuple(selected)


def _task_from_dict(raw: Any) -> BenchmarkTask:
    """将一个 JSON 对象转为任务；坏字段统一拒绝。"""
    if not isinstance(raw, dict):
        raise ValueError("任务必须是对象")
    required = {
        "id",
        "route",
        "instruction",
        "initial_state",
        "success",
        "forbidden_actions",
        "max_tool_calls",
        "timeout_seconds",
        "category",
        "difficulty",
    }
    if not required.issubset(raw):
        raise ValueError("任务字段不完整")
    if raw["category"] not in REQUIRED_CATEGORIES or not str(raw["route"]).startswith("/"):
        raise ValueError("任务类别或路由无效")
    if not isinstance(raw["initial_state"], dict) or not isinstance(raw["success"], dict):
        raise ValueError("任务状态和断言必须是对象")
    if not isinstance(raw["forbidden_actions"], list) or not all(
        isinstance(x, str) for x in raw["forbidden_actions"]
    ):
        raise ValueError("禁止动作必须是字符串列表")
    if int(raw["max_tool_calls"]) <= 0 or int(raw["timeout_seconds"]) <= 0:
        raise ValueError("任务上限必须为正数")
    return BenchmarkTask(
        id=str(raw["id"]),
        route=str(raw["route"]),
        instruction=str(raw["instruction"]),
        initial_state=dict(raw["initial_state"]),
        success=dict(raw["success"]),
        forbidden_actions=tuple(raw["forbidden_actions"]),
        max_tool_calls=int(raw["max_tool_calls"]),
        timeout_seconds=int(raw["timeout_seconds"]),
        category=str(raw["category"]),
        difficulty=str(raw["difficulty"]),
    )
