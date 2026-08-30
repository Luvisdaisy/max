"""以既有 AgentRunner 运行单题并收集可审计指标。"""

from __future__ import annotations

import asyncio
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from max_gui.agent.graph import AgentRunner
from max_gui.benchmark.evaluator import score_state
from max_gui.benchmark.report import TaskResult, termination_reason
from max_gui.benchmark.tasks import BenchmarkTask, TaskSuite
from max_gui.observability import RunEvent
from max_gui.session.store import SessionStore

StateReader = Callable[[BenchmarkTask], Awaitable[dict[str, object]]]
ACTION_TOOLS = {"mouse_click", "mouse_scroll", "keyboard_type", "keyboard_press", "task_complete"}


def validate_comparison(base: dict[str, object], lora: dict[str, object]) -> None:
    """确认基线与 LoRA 运行条件一致；模型名允许不同。"""
    keys = ("suite_version", "temperature", "max_iterations", "timeout_seconds", "browser")
    mismatched = [key for key in keys if base.get(key) != lora.get(key)]
    if mismatched:
        raise ValueError(f"模型对比条件不一致：{', '.join(mismatched)}")


@contextmanager
def open_benchmark_browser(url: str, *, browser: str = "Google Chrome") -> Iterator[Path]:
    """以专用 profile 启动 Chrome，确认进程存活后在退出时清理。

    参数：`url` 必须是回环评测地址；`browser` 仅用于 macOS 应用名定位。
    返回：当前题独占的 profile 路径。
    异常：非 macOS、非回环地址、找不到 Chrome 或启动失败时抛出运行时异常。
    副作用：启动并在上下文退出时终止一个 Chrome 子进程。
    """
    if platform.system() != "Darwin":
        raise RuntimeError("真实浏览器评测仅支持在 macOS 专用环境运行")
    if not url.startswith("http://127.0.0.1:"):
        raise ValueError("评测页面必须使用 127.0.0.1 回环地址")
    app_binary = Path(f"/Applications/{browser}.app/Contents/MacOS/{browser}")
    if not app_binary.is_file():
        raise RuntimeError(f"未找到评测浏览器：{app_binary}")
    profile = Path(tempfile.mkdtemp(prefix="max-gui-benchmark-"))
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            [
                str(app_binary),
                f"--user-data-dir={profile}",
                "--window-size=1440,960",
                "--force-device-scale-factor=1",
                "--lang=zh-CN",
                "--no-first-run",
                "--no-default-browser-check",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.4)
        if process.poll() is not None:
            raise RuntimeError("评测浏览器启动后立即退出")
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status >= 400:
                    raise RuntimeError(f"评测页面不可观察：HTTP {response.status}")
        except (OSError, urllib.error.URLError) as exc:
            raise RuntimeError("评测页面不可观察，请检查本地服务") from exc
        yield profile
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        shutil.rmtree(profile, ignore_errors=True)


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
    guard_state = {"actions": 0, "limit_hit": False, "violations": []}

    def tool_guard(name: str, _arguments: dict[str, object]) -> str | None:
        """在工具实际执行前阻断本题违规和超过预算的动作。"""
        if name in task.forbidden_actions:
            guard_state["violations"].append(name)
            runner.interrupt()
            return f"评测已阻止禁止动作：{name}"
        if name in ACTION_TOOLS:
            if guard_state["actions"] >= task.max_tool_calls:
                guard_state["limit_hit"] = True
                runner.interrupt()
                return f"评测动作上限为 {task.max_tool_calls}，当前请求未执行"
            guard_state["actions"] += 1
        return None

    try:
        state = await asyncio.wait_for(
            runner.run(
                session,
                user_text=task.instruction,
                on_event=events.append,
                tool_guard=tool_guard,
            ),
            timeout=task.timeout_seconds,
        )
    except TimeoutError:
        runner.interrupt()
        timed_out = True
        state = {"status": "error"}
    summary = _terminal_summary(events)
    tool_calls = int(summary.get("tool_calls") or 0)
    violations = list(guard_state["violations"]) + [
        name for name in task.forbidden_actions if _called(events, name)
    ]
    reason = termination_reason(
        agent_status=str(state.get("status") or "error"),
        tool_calls=tool_calls,
        limit=task.max_tool_calls,
        violations=violations,
        timed_out=timed_out,
        limit_hit=bool(guard_state["limit_hit"]),
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
        tool_calls=max(tool_calls, int(guard_state["actions"])),
        tool_failures=int(summary.get("tool_failures") or 0),
        invalid_actions=len(violations),
        violations=tuple(violations),
        total_tokens=_tokens(summary),
        difficulty=task.difficulty,
        category=task.category,
        capabilities=task.capabilities,
        task_family=task.task_family,
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
