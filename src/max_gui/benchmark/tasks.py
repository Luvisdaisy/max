"""版本化 v2 Web GUI 任务的加载、覆盖校验与批次选择。

任务文件逐条列出全部 100 项；加载过程绝不复制、展开或随机生成任务。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SUITE = PROJECT_ROOT / "artifacts" / "benchmarks" / "web-gui-v2.json"
REQUIRED_DIFFICULTIES = {"easy", "medium", "hard"}
REQUIRED_CAPABILITIES = {
    "navigation",
    "observe",
    "click",
    "text_input",
    "selection",
    "filter",
    "sort",
    "pagination",
    "edit",
    "batch",
    "confirmation",
    "validation",
    "workflow",
}
REQUIRED_WORKFLOWS = {
    "project_context",
    "member_workload",
    "empty_filter",
    "validation_recovery",
    "undo",
    "subtasks",
    "fact_driven_edit",
}
FORBIDDEN_FIELDS = {"copies_per_template", "templates", "variants"}


@dataclass(frozen=True, slots=True)
class BenchmarkTask:
    """一条可独立重置和判分的显式 GUI 评测任务。"""

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
    capabilities: tuple[str, ...]
    expected_steps: int
    required_checkpoints: tuple[str, ...]
    smoke: bool
    task_family: str
    information_dependency: str | None
    recovery_path: str | None


@dataclass(frozen=True, slots=True)
class TaskSuite:
    """带版本号的不可变任务集合。"""

    version: str
    tasks: tuple[BenchmarkTask, ...]


def load_task_suite(path: Path = DEFAULT_SUITE) -> TaskSuite:
    """读取并严格校验 100 条显式 v2 任务。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("version"), str):
        raise ValueError("任务集必须含字符串 version")
    if FORBIDDEN_FIELDS.intersection(raw):
        raise ValueError("v2 任务集不得包含复制或模板展开字段")
    entries = raw.get("tasks")
    if not isinstance(entries, list) or len(entries) != 100:
        raise ValueError("v2 任务集必须显式包含恰好 100 条任务")
    tasks = tuple(_task_from_dict(item) for item in entries)
    if len({task.id for task in tasks}) != len(tasks):
        raise ValueError("任务标识不得重复")
    if {task.difficulty for task in tasks} != REQUIRED_DIFFICULTIES:
        raise ValueError("任务集必须覆盖 easy、medium、hard 三种难度")
    capabilities = {capability for task in tasks for capability in task.capabilities}
    if not REQUIRED_CAPABILITIES.issubset(capabilities):
        raise ValueError("任务集缺少规定的能力覆盖")
    instructions = [task.instruction.strip() for task in tasks]
    if len(set(instructions)) != len(instructions):
        raise ValueError("任务指令不得重复")
    smoke = tuple(task for task in tasks if task.smoke)
    if len(smoke) != 10 or {task.difficulty for task in smoke} != REQUIRED_DIFFICULTIES:
        raise ValueError("冒烟任务必须为 10 条且覆盖三种难度")
    smoke_capabilities = {capability for task in smoke for capability in task.capabilities}
    if not REQUIRED_CAPABILITIES.issubset(smoke_capabilities):
        raise ValueError("冒烟任务缺少规定的能力覆盖")
    workflows = {
        label
        for task in tasks
        for label in (task.task_family, task.information_dependency, task.recovery_path)
        if label
    }
    if not REQUIRED_WORKFLOWS.issubset(workflows):
        missing = "、".join(sorted(REQUIRED_WORKFLOWS - workflows))
        raise ValueError(f"任务集缺少复杂工作流覆盖：{missing}")
    smoke_workflows = {
        label
        for task in smoke
        for label in (task.task_family, task.information_dependency, task.recovery_path)
        if label
    }
    required_smoke = {"fact_driven_edit", "validation_recovery", "undo", "subtasks"}
    if not required_smoke.issubset(smoke_workflows):
        missing = "、".join(sorted(required_smoke - smoke_workflows))
        raise ValueError(f"冒烟任务缺少关键复杂路径：{missing}")
    return TaskSuite(version=raw["version"], tasks=tasks)


def select_task_batch(suite: TaskSuite, task_count: int) -> tuple[BenchmarkTask, ...]:
    """选择唯一支持的 10 条固定冒烟批次或完整 100 条任务集。"""
    if task_count == 100:
        return suite.tasks
    if task_count == 10:
        return tuple(task for task in suite.tasks if task.smoke)
    raise ValueError("任务数量仅支持 10 或 100")


def _task_from_dict(raw: Any) -> BenchmarkTask:
    """把单条 JSON 任务转换为强类型记录并拒绝不完整字段。"""
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
        "capabilities",
        "expected_steps",
        "required_checkpoints",
        "smoke",
        "task_family",
        "information_dependency",
        "recovery_path",
    }
    if not required.issubset(raw):
        raise ValueError("任务字段不完整")
    if raw["difficulty"] not in REQUIRED_DIFFICULTIES or raw["route"] != "/arena/home":
        raise ValueError("任务难度或路由无效")
    instruction = str(raw["instruction"]).strip()
    if not instruction or any(
        marker in instruction for marker in ("本题对象为", "/arena/", "last_action")
    ):
        raise ValueError("任务指令必须是自然语言目标且不得暴露内部信息")
    if not isinstance(raw["initial_state"], dict) or not isinstance(raw["success"], dict):
        raise ValueError("任务状态和断言必须是对象")
    if not isinstance(raw["capabilities"], list) or not all(
        isinstance(item, str) for item in raw["capabilities"]
    ):
        raise ValueError("能力标签必须是字符串列表")
    if not isinstance(raw["forbidden_actions"], list) or not all(
        isinstance(item, str) for item in raw["forbidden_actions"]
    ):
        raise ValueError("禁止动作必须是字符串列表")
    if int(raw["max_tool_calls"]) <= 0 or int(raw["timeout_seconds"]) <= 0:
        raise ValueError("任务上限必须为正数")
    expected_steps = int(raw["expected_steps"])
    step_ranges = {"easy": range(1, 4), "medium": range(5, 7)}
    if raw["difficulty"] in step_ranges and expected_steps not in step_ranges[raw["difficulty"]]:
        raise ValueError("任务预期操作数不符合难度范围")
    if raw["difficulty"] == "hard" and expected_steps < 7:
        raise ValueError("高级任务至少需要 7 个主要可见操作")
    checkpoints = raw["required_checkpoints"]
    if not isinstance(checkpoints, list) or not all(isinstance(item, str) for item in checkpoints):
        raise ValueError("必要检查点必须是字符串列表")
    if raw["difficulty"] == "medium" and len(raw["capabilities"]) < 2:
        raise ValueError("中等任务至少组合两种能力")
    if raw["difficulty"] == "hard" and sum(item.startswith("visited_") for item in checkpoints) < 2:
        raise ValueError("高级任务至少包含两个跨页导航检查点")
    task_family = raw["task_family"]
    dependency = raw["information_dependency"]
    recovery = raw["recovery_path"]
    if not isinstance(task_family, str) or not task_family:
        raise ValueError("任务族必须为非空字符串")
    if dependency is not None and not isinstance(dependency, str):
        raise ValueError("信息依赖必须为字符串或 null")
    if recovery is not None and not isinstance(recovery, str):
        raise ValueError("恢复路径必须为字符串或 null")
    return BenchmarkTask(
        id=str(raw["id"]),
        route=str(raw["route"]),
        instruction=instruction,
        initial_state=dict(raw["initial_state"]),
        success=dict(raw["success"]),
        forbidden_actions=tuple(raw["forbidden_actions"]),
        max_tool_calls=int(raw["max_tool_calls"]),
        timeout_seconds=int(raw["timeout_seconds"]),
        category=str(raw["category"]),
        difficulty=str(raw["difficulty"]),
        capabilities=tuple(raw["capabilities"]),
        expected_steps=expected_steps,
        required_checkpoints=tuple(checkpoints),
        smoke=bool(raw["smoke"]),
        task_family=task_family,
        information_dependency=dependency,
        recovery_path=recovery,
    )
