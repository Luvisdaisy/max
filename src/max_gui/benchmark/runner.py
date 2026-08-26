"""以既有 AgentRunner 运行单题并收集可审计指标。"""

from __future__ import annotations

import asyncio
import platform
import subprocess
from collections.abc import Awaitable, Callable

from max_gui.agent.graph import AgentRunner
from max_gui.benchmark.evaluator import score_state
from max_gui.benchmark.report import TaskResult, termination_reason
from max_gui.benchmark.tasks import BenchmarkTask, TaskSuite
from max_gui.observability import RunEvent
from max_gui.session.store import SessionStore

StateReader = Callable[[BenchmarkTask], Awaitable[dict[str, object]]]


def validate_comparison(base: dict[str, object], lora: dict[str, object]) -> None:
    """确认基线与 LoRA 运行条件一致；模型名允许不同。"""
    keys = ("suite_version", "temperature", "max_iterations", "timeout_seconds", "browser")
    mismatched = [key for key in keys if base.get(key) != lora.get(key)]
    if mismatched:
        raise ValueError(f"模型对比条件不一致：{', '.join(mismatched)}")


def open_benchmark_browser(url: str, *, browser: str = "Google Chrome") -> None:
    """显式启动专用 macOS 浏览器窗口；非 macOS 或非法回环地址拒绝执行。"""
    if platform.system() != "Darwin":
        raise RuntimeError("真实浏览器评测仅支持在 macOS 专用环境运行")
    if not url.startswith("http://127.0.0.1:"):
        raise ValueError("评测页面必须使用 127.0.0.1 回环地址")
    subprocess.run(["open", "-a", browser, url], check=True)


async def run_task(
    runner: AgentRunner,
    store: SessionStore,
    suite: TaskSuite,
    task: BenchmarkTask,
    read_state: StateReader,
    *,
    model: str,
) -> TaskResult:
    """运行一题并按独立业务状态评分；调用方负责浏览器重置与打开页面。"""
    events: list[RunEvent] = []
    session = store.create(model=model)
    timed_out = False
    try:
        state = await asyncio.wait_for(
            runner.run(session, user_text=task.instruction, on_event=events.append),
            timeout=task.timeout_seconds,
        )
    except TimeoutError:
        runner.interrupt()
        timed_out = True
        state = {"status": "error"}
    summary = _terminal_summary(events)
    tool_calls = int(summary.get("tool_calls") or 0)
    violations = [name for name in task.forbidden_actions if _called(events, name)]
    reason = termination_reason(
        agent_status=str(state.get("status") or "error"),
        tool_calls=tool_calls,
        limit=task.max_tool_calls,
        violations=violations,
        timed_out=timed_out,
    )
    business = await read_state(task)
    score = score_state(business, task.success)
    return TaskResult(
        task_id=task.id,
        suite_version=suite.version,
        model=model,
        strict_success=score.strict_success and reason == "completed",
        criteria_passed=score.criteria_passed,
        criteria_total=score.criteria_total,
        termination_reason=reason,
        duration_ms=int(summary.get("duration_ms") or 0),
        tool_calls=tool_calls,
        tool_failures=int(summary.get("tool_failures") or 0),
        invalid_actions=0,
        violations=tuple(violations),
        total_tokens=_tokens(summary),
    )


def _called(events: list[RunEvent], tool_name: str) -> bool:
    """检查运行事件是否调过指定工具。"""
    return any(event.data.get("tool_name") == tool_name for event in events)


def _terminal_summary(events: list[RunEvent]) -> dict[str, object]:
    """取最后一条运行终态的汇总；无终态时返回空字典。"""
    for event in reversed(events):
        if event.event_type in {"run.completed", "run.failed", "run.interrupted"}:
            return event.data
    return {}


def _tokens(summary: dict[str, object]) -> int | None:
    """只在终态有完整非负整数用量时返回 Token 总量。"""
    total = summary.get("total_tokens")
    return total if isinstance(total, int) and total >= 0 else None
