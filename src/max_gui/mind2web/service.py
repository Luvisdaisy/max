"""Online-Mind2Web 单题与批次执行编排。

真实执行必须由 CLI 的 `--run` 明确开启；默认仅生成预检和报告，因此不会意外打开外网浏览器。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from max_gui.agent.graph import AgentRunner
from max_gui.config import Settings
from max_gui.inference.client import InferenceClient
from max_gui.mind2web.browser import IsolatedChrome, UrlObserver
from max_gui.mind2web.models import (
    EvaluationSummary,
    OnlineMind2WebTask,
    PreflightStatus,
    TaskMetrics,
)
from max_gui.mind2web.preflight import RuntimeSafetyGuard, is_allowed_url, plan_preflight
from max_gui.mind2web.report import write_reports
from max_gui.mind2web.tasks import load_safety_manifest, load_tasks
from max_gui.mind2web.trajectory import EvaluationStepRecorder, TrajectoryValidationError
from max_gui.mind2web.webjudge import WebJudgeError, run_webjudge
from max_gui.session.store import SessionStore
from max_gui.tools.registry import AutoApproveGate, build_default_registry


def evaluate(
    settings: Settings,
    *,
    tasks_path: Path,
    safety_path: Path,
    output_root: Path,
    run: bool,
    chrome_path: str | None = None,
    judge: bool = False,
    judge_model: str | None = None,
    judge_api_key_env: str = "OPENAI_API_KEY",
) -> Path:
    """执行或仅预检一批用户指定的 Online-Mind2Web 任务。

    参数：`run` 为假时绝不启动浏览器或 Agent；为真时每题使用新隔离 profile。
    返回：本次独立结果目录。
    """
    tasks, tasks_digest = load_tasks(tasks_path, authorized_root=settings.project_root)
    manifest, safety_digest = load_safety_manifest(
        safety_path, authorized_root=settings.project_root
    )
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    results = asyncio.run(
        _evaluate_all(settings, tasks, manifest, output_dir, run=run, chrome_path=chrome_path)
    )
    upstream = settings.project_root / "artifacts" / "Online-Mind2Web"
    if judge:
        results = _judge_results(
            results,
            upstream=upstream,
            trajectories_dir=output_dir / "trajectories",
            output_dir=output_dir / "webjudge",
            judge_model=judge_model or settings.model_name,
            api_key_env=judge_api_key_env,
        )
    else:
        results = [
            replace(item, judge_status=PreflightStatus.JUDGE_PENDING)
            if item.trajectory_status is PreflightStatus.TRAJECTORY_VALID
            else item
            for item in results
        ]
    summary = EvaluationSummary(planned_tasks=len(tasks), results=results)
    write_reports(
        output_dir,
        {
            "run_id": run_id,
            "tasks_path": str(tasks_path.resolve()),
            "tasks_sha256": tasks_digest,
            "safety_path": str(safety_path.resolve()),
            "safety_sha256": safety_digest,
            "model": settings.model_name,
            "provider": settings.provider,
            "run_enabled": run,
            "judge_enabled": judge,
            "judge_model": judge_model if judge else None,
            "upstream_path": str(upstream),
            "upstream_marker": _upstream_marker(upstream),
        },
        summary,
    )
    return output_dir


async def _evaluate_all(
    settings: Settings,
    tasks: tuple[OnlineMind2WebTask, ...],
    manifest: Any,
    output_dir: Path,
    *,
    run: bool,
    chrome_path: str | None,
) -> list[TaskMetrics]:
    """顺序预检并执行题目；题间绝不复用 Chrome profile。"""
    results: list[TaskMetrics] = []
    for index, task in enumerate(tasks):
        preflight = plan_preflight(task, manifest)
        (output_dir / "preflight.json").write_text(
            json.dumps(
                [{"task_id": item.task_id, "status": item.preflight_status} for item in results]
                + [
                    {
                        "task_id": task.task_id,
                        "status": preflight.status,
                        "detail": preflight.detail,
                    }
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if not preflight.is_ready or not run:
            results.append(
                TaskMetrics(
                    task.task_id,
                    preflight.status,
                    reference_length=task.reference_length,
                    detail=preflight.detail,
                )
            )
            continue
        results.append(
            await _run_one(
                settings, task, manifest.rule_for(task.task_id), output_dir, index, chrome_path
            )
        )
    return results


async def _run_one(
    settings: Settings,
    task: OnlineMind2WebTask,
    rule: Any,
    output_dir: Path,
    index: int,
    chrome_path: str | None,
) -> TaskMetrics:
    """在一题专用浏览器中调用既有 AgentRunner，并导出轨迹。"""
    started = time.perf_counter()
    port = 19000 + index
    task_dir = output_dir / "trajectories" / task.task_id
    try:
        with IsolatedChrome(port, chrome_path) as chrome:
            chrome.start(task.website)
            observer = UrlObserver(port)
            initial_url = await _await_initial_url(observer)
            if not initial_url or not is_allowed_url(initial_url, rule):
                return _metric(
                    task,
                    PreflightStatus.ENVIRONMENT_ERROR,
                    started,
                    detail="隔离 Chrome 未在允许域提供可观察的起始 URL",
                )
            recorder = EvaluationStepRecorder(task, rule, task_dir, observer.current_url)
            store = SessionStore(settings.sessions_dir)
            runner = AgentRunner(
                settings,
                InferenceClient(settings),
                build_default_registry(settings, gate=AutoApproveGate()),
                store,
            )
            session = store.create(model=settings.model_name)
            guard = RuntimeSafetyGuard(rule, observer.current_url, runner.interrupt)
            try:
                state = await asyncio.wait_for(
                    runner.run(
                        session,
                        user_text=task.instruction,
                        on_evaluation_step=recorder.record,
                        tool_guard=guard,
                    ),
                    timeout=rule.timeout_seconds,
                )
            except TimeoutError:
                runner.interrupt()
                return _metric(task, PreflightStatus.INTERRUPTED, started, detail="任务超时")
            if any(
                item.get("content", {}).get("exec", {}).get("code") == "evaluation_safety_blocked"
                for item in state.get("messages", [])
                if isinstance(item, dict)
            ):
                return _metric(
                    task,
                    guard.last_status or PreflightStatus.UNSAFE_ACTION_RISK,
                    started,
                    detail="运行时安全护栏阻断",
                )
            if state.get("status") == "interrupted":
                return _metric(task, PreflightStatus.INTERRUPTED, started, detail="用户中断")
            try:
                recorder.write_and_validate()
            except TrajectoryValidationError as exc:
                status = (
                    PreflightStatus.MODEL_INCOMPLETE
                    if not recorder.completion_declared
                    else PreflightStatus.MODEL_ERROR
                )
                return _metric(task, status, started, detail=str(exc))
            summary = session.run_summary or {}
            return TaskMetrics(
                task.task_id,
                PreflightStatus.READY,
                execution_status=PreflightStatus.READY,
                executed=True,
                duration_ms=int((time.perf_counter() - started) * 1000),
                tool_calls=int(summary.get("tool_calls") or 0),
                total_tokens=summary.get("total_tokens"),
                action_steps=len(recorder.steps),
                reference_length=task.reference_length,
                trajectory_status=PreflightStatus.TRAJECTORY_VALID,
            )
    except Exception as exc:
        return _metric(task, PreflightStatus.ENVIRONMENT_ERROR, started, detail=str(exc))


def _metric(
    task: OnlineMind2WebTask, status: PreflightStatus, started: float, *, detail: str
) -> TaskMetrics:
    """构造执行未完成的统一任务指标。"""
    return TaskMetrics(
        task.task_id,
        PreflightStatus.READY,
        execution_status=status,
        executed=True,
        duration_ms=int((time.perf_counter() - started) * 1000),
        reference_length=task.reference_length,
        detail=detail,
    )


async def _await_initial_url(observer: UrlObserver, attempts: int = 10) -> str | None:
    """轮询回环观察器，确认专用 Chrome 已加载可审计起始页面。"""
    for _ in range(attempts):
        try:
            if url := observer.current_url():
                return url
        except Exception:
            pass
        await asyncio.sleep(0.3)
    return None


def _judge_results(
    results: list[TaskMetrics],
    *,
    upstream: Path,
    trajectories_dir: Path,
    output_dir: Path,
    judge_model: str,
    api_key_env: str,
) -> list[TaskMetrics]:
    """调用显式 Judge，并把标签或错误回填到已验证轨迹。"""
    eligible = [
        item for item in results if item.trajectory_status is PreflightStatus.TRAJECTORY_VALID
    ]
    if not eligible:
        return results
    try:
        labels = run_webjudge(
            upstream_root=upstream,
            trajectories_dir=trajectories_dir,
            output_path=output_dir,
            judge_model=judge_model,
            api_key_env=api_key_env,
        )
    except WebJudgeError as exc:
        return [
            replace(
                item, judge_status=PreflightStatus.WEBJUDGE_ERROR, detail=item.detail or str(exc)
            )
            if item in eligible
            else item
            for item in results
        ]
    return [
        replace(
            item,
            judge_status=PreflightStatus.JUDGED,
            webjudge_label=labels.get(item.task_id),
        )
        if item in eligible and item.task_id in labels
        else replace(
            item, judge_status=PreflightStatus.WEBJUDGE_ERROR, detail="WebJudge 未回填本题标签"
        )
        if item in eligible
        else item
        for item in results
    ]


def _upstream_marker(upstream: Path) -> str | None:
    """记录上游目录的不可逆简要标识，不修改其任何文件。"""
    readme = upstream / "README.md"
    if not readme.is_file():
        return None
    return hashlib.sha256(readme.read_bytes()).hexdigest()
