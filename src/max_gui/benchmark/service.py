"""由评测首页显式选择规模并触发的浏览器评测协调器。"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import uvicorn

from max_gui.agent.graph import AgentRunner
from max_gui.benchmark.report import TaskResult, write_report
from max_gui.benchmark.runner import open_benchmark_browser, run_task
from max_gui.benchmark.tasks import BenchmarkTask, TaskSuite, load_task_suite, select_task_batch
from max_gui.benchmark.web import BenchmarkStore, create_benchmark_app
from max_gui.config import Settings
from max_gui.inference.client import InferenceClient
from max_gui.session.store import SessionStore
from max_gui.tools.registry import AutoApproveGate, build_default_registry


class BenchmarkController:
    """串行执行任务，并向首页公开最小进度。"""

    def __init__(
        self, settings: Settings, suite: TaskSuite, store: BenchmarkStore, base_url: str
    ) -> None:
        """注入运行配置、任务集合、页面状态与回环地址。"""
        self.settings, self.suite, self.store, self.base_url = settings, suite, store, base_url
        self._status: dict[str, Any] = {
            "status": "ready",
            "completed": 0,
            "total": 0,
        }
        self._lock = threading.Lock()
        self._interrupt_requested = threading.Event()
        self._runner: AgentRunner | None = None

    def progress(self) -> dict[str, Any]:
        """返回首页显示用进度副本。"""
        with self._lock:
            return dict(self._status)

    def start(self, task_count: int) -> bool:
        """按首页选择启动一个后台批次，运行中重复请求返回假。

        参数：`task_count` 仅支持 10 或 100。
        返回：成功创建后台批次时为真；已有运行中的批次时为假。
        异常：任务数量不受支持或任务集不能满足选择条件时抛出 `ValueError`。
        """
        tasks = select_task_batch(self.suite, task_count)
        with self._lock:
            if self._status["status"] in {"running", "interrupting"}:
                return False
            self._interrupt_requested.clear()
            self._status.update(
                status="running",
                completed=0,
                total=len(tasks),
                current_task=None,
                report_path=None,
            )
        threading.Thread(target=lambda: asyncio.run(self._run_all(tasks)), daemon=True).start()
        return True

    def interrupt(self) -> bool:
        """请求中断当前批次，并将请求转发给正在运行的 Agent。

        返回：运行中的批次成功收到请求时为真；空闲或已结束时为假。
        副作用：当前题会在 Agent 支持的下一个中断点结束，后续题目不会启动。
        """
        with self._lock:
            if self._status["status"] != "running":
                return False
            self._interrupt_requested.set()
            self._status["status"] = "interrupting"
            runner = self._runner
        if runner is not None:
            runner.interrupt()
        return True

    async def _run_all(self, tasks: tuple[BenchmarkTask, ...]) -> None:
        """重置、打开页面并通过真实 AgentRunner 顺序执行所选任务。"""
        results: list[TaskResult] = []
        sessions = SessionStore(self.settings.sessions_dir)
        runner = AgentRunner(
            self.settings,
            InferenceClient(self.settings),
            build_default_registry(self.settings, gate=AutoApproveGate()),
            sessions,
        )
        with self._lock:
            self._runner = runner
        if self._interrupt_requested.is_set():
            runner.interrupt()
        try:
            for index, task in enumerate(tasks, start=1):
                if self._interrupt_requested.is_set():
                    break
                self.store.reset(task.id)
                with self._lock:
                    self._status.update(completed=index - 1, current_task=task.id)
                open_benchmark_browser(f"{self.base_url}/arena/home")
                await asyncio.sleep(1)
                results.append(
                    await run_task(
                        runner,
                        sessions,
                        self.suite,
                        task,
                        self._read_state,
                        model=self.settings.model_name,
                    )
                )
                if self._interrupt_requested.is_set():
                    break
            task_count = len(tasks)
            report = (
                self.settings.project_root
                / "artifacts"
                / "reports"
                / f"web-gui-eval-{task_count}.json"
            )
            write_report(results, report, requested_tasks=task_count)
            with self._lock:
                self._status.update(
                    status="interrupted" if self._interrupt_requested.is_set() else "completed",
                    completed=len(results),
                    report_path=str(report),
                )
        except Exception as exc:
            with self._lock:
                self._status.update(status="failed", error=str(exc))
        finally:
            with self._lock:
                self._runner = None

    async def _read_state(self, task: BenchmarkTask) -> dict[str, object]:
        """向评分器提供当前任务的业务状态副本。"""
        return dict(self.store.state)


def run_benchmark_server(settings: Settings, *, port: int = 8765) -> None:
    """启动等待用户从首页选择 10 或 100 条任务的回环评测服务。"""
    suite = load_task_suite()
    app = create_benchmark_app(suite)
    controller = BenchmarkController(
        settings, suite, app.state.benchmark_store, f"http://127.0.0.1:{port}"
    )
    app = create_benchmark_app(
        suite, start=controller.start, progress=controller.progress, interrupt=controller.interrupt
    )
    controller.store = app.state.benchmark_store
    uvicorn.run(app, host="127.0.0.1", port=port)
