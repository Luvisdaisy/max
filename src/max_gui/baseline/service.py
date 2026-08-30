"""五题真实桌面基线评测的顺序编排入口。"""

from __future__ import annotations

import asyncio
import platform
import sys
import termios
import time
import tty
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from max_gui.agent.graph import AgentRunner
from max_gui.baseline.environment import BaselineEnvironment
from max_gui.baseline.models import (
    BaselineResult,
    BaselineStatus,
    BaselineTask,
    ReviewVerdict,
    RiskLevel,
)
from max_gui.baseline.report import write_run_record
from max_gui.baseline.review import review_screenshot
from max_gui.baseline.tasks import DEFAULT_TASKS, load_tasks
from max_gui.config import Settings
from max_gui.inference.client import InferenceClient
from max_gui.inference.retry import safe_retry_detail
from max_gui.session.store import SessionStore
from max_gui.tools.protocol import ToolResult
from max_gui.tools.registry import AutoApproveGate, build_default_registry

REVIEW_COOLDOWN_SECONDS = 60
INTERRUPT_GRACE_SECONDS = 5

ACTION_TOOLS = frozenset(
    {
        "mouse_click",
        "mouse_drag",
        "mouse_scroll",
        "keyboard_type",
        "keyboard_press",
        "type_text",
        "press_key",
        "press_shortcut",
    }
)

WINDOW_HINTS = {
    "weather": "Google Chrome 浏览器",
    "terminal": "Terminal",
    "calculator": "Calculator",
    "reminders": "Reminders",
    "wechat": "WeChat 文件传输助手",
}


def run_baseline(
    settings: Settings,
    *,
    rounds: int = 1,
    task_confirm: Callable[[BaselineTask, str], bool] | None = None,
    tasks_path: Path = DEFAULT_TASKS,
) -> Path:
    """经显式确认运行一至多轮真实基线任务并返回唯一 JSON 记录。

    参数：`task_confirm` 为每题窗口前置确认函数，可由测试或 CLI 注入。
    启动后直接进入首题；单题确认拒绝时仅安全阻断当前题。
    异常：轮次数非正或任务契约无效时抛出 `ValueError`。
    """
    if rounds <= 0:
        raise ValueError("基线评测轮次数必须为正整数")
    tasks, digest = load_tasks(tasks_path)
    if task_confirm is None:
        task_confirm = _terminal_task_confirm
    batch_id = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    root = settings.project_root / "artifacts" / "evaluations" / "baseline-desktop"
    root.mkdir(parents=True, exist_ok=True)
    output = root / f"{batch_id}.json"
    if output.exists():
        output = root / f"{batch_id}-{uuid4().hex[:6]}.json"
    results = asyncio.run(_run_all(settings, tasks, rounds, task_confirm))
    write_run_record(
        output,
        {
            "batch_id": batch_id,
            "task_file": str(tasks_path.resolve()),
            "task_sha256": digest,
            "provider": settings.provider,
            "model": settings.model_name,
            "rounds": rounds,
            "platform": platform.platform(),
            "display_note": "真实桌面显示条件由截图证据记录；不读取个人应用数据库。",
        },
        results,
    )
    return output


async def _run_all(
    settings: Settings,
    tasks: tuple[BaselineTask, ...],
    rounds: int,
    task_confirm: Callable[[BaselineTask, str], bool],
) -> list[BaselineResult]:
    """按轮、按稳定顺序等待窗口确认后运行；个人写入护栏仅在单轮内生效。"""
    results: list[BaselineResult] = []
    run_date = datetime.now().astimezone().date().isoformat()
    for number in range(1, rounds + 1):
        environment = BaselineEnvironment(allow_personal_write=True)
        round_id = f"round-{number:03d}"
        for task in tasks:
            nonce = f"{round_id}-{uuid4().hex[:6]}"
            if not task_confirm(task, round_id):
                result = _blocked(
                    task,
                    round_id,
                    nonce,
                    BaselineStatus.SAFETY_BLOCKED,
                    "用户未确认所需窗口已前置",
                    time.perf_counter(),
                )
            else:
                result = await _run_one(settings, task, environment, round_id, nonce, run_date)
            results.append(result)
            _announce_result(result)
    return results


async def _run_one(
    settings: Settings,
    task: BaselineTask,
    environment: BaselineEnvironment,
    round_id: str,
    nonce: str,
    run_date: str,
) -> BaselineResult:
    """执行单题，温和中断后截取终态，并恰好调用一次独立评审。"""
    started = time.perf_counter()
    preflight, detail = environment.preflight(task)
    if preflight is not BaselineStatus.READY:
        return _blocked(task, round_id, nonce, preflight, detail, started)
    environment.mark_write(task)
    events: list[Any] = []
    store = SessionStore(settings.sessions_dir)
    registry = build_default_registry(settings, gate=AutoApproveGate())
    retry_settings = replace(settings, inference_max_retries=2)
    runner = AgentRunner(retry_settings, InferenceClient(retry_settings), registry, store)
    session = store.create(model=settings.model_name, title=f"基线：{task.id}")
    guard = _guard(task, nonce)
    state: dict[str, Any] = {}
    status = BaselineStatus.AGENT_ERROR
    detail = ""
    task_run = asyncio.create_task(
        runner.run(
            session,
            user_text=task.render_prompt(nonce, run_date),
            on_event=events.append,
            tool_guard=guard,
        )
    )
    try:
        state = await asyncio.wait_for(asyncio.shield(task_run), timeout=task.timeout_seconds)
        status = _status(state, guard)
    except Exception as exc:
        if isinstance(exc, TimeoutError):
            runner.interrupt()
            status = BaselineStatus.TIMEOUT
            detail = "执行超过 180 秒，已请求 Agent 收尾"
            try:
                state = await asyncio.wait_for(task_run, timeout=INTERRUPT_GRACE_SECONDS)
            except TimeoutError:
                task_run.cancel()
                status = BaselineStatus.TIMEOUT_FORCED
                detail = "执行超过 180 秒，Agent 未在收尾窗口停止"
            except Exception as grace_exc:
                detail = f"执行超时后收尾失败：{safe_retry_detail(grace_exc)}"
        else:
            detail = f"LLM 调用失败：{safe_retry_detail(exc)}"
    screenshot = await _capture_terminal_screenshot(registry)
    screenshot_source = "post_termination_snapshot" if screenshot else None
    if screenshot is None:
        screenshot = _last_screenshot(state)
        screenshot_source = "agent_observation" if screenshot else None
    claimed = bool((state.get("task_context") or {}).get("completion_verified"))
    review = None
    if screenshot is not None:
        if REVIEW_COOLDOWN_SECONDS:
            await asyncio.sleep(REVIEW_COOLDOWN_SECONDS)
        review_settings = replace(settings, inference_max_retries=2)
        review = await review_screenshot(
            InferenceClient(review_settings),
            review_settings,
            rubric=task.render_rubric(nonce, run_date),
            image=screenshot,
            run_date=run_date,
        )
    return _result(
        task,
        round_id,
        nonce,
        status,
        started,
        session,
        guard,
        screenshot,
        screenshot_source,
        detail,
        claimed,
        review,
    )


def _announce_result(result: BaselineResult) -> None:
    """在独立截图评审完成后输出当前题的成功或失败结论。"""
    verdict = "成功" if result.success else "失败"
    reason = result.detail or str(result.execution_status or result.preflight_status)
    print(f"[{result.round_id}/{result.task_id}] 结果：{verdict}（{reason}）")


def _guard(task: BaselineTask, nonce: str) -> Callable[[str, dict[str, object]], str | None]:
    """在桌面工具实际执行前限制个人写入重放与关键输入文本。"""
    state = {"actions": 0, "violations": []}

    def guard(name: str, arguments: dict[str, object]) -> str | None:
        """记录步长，并拒绝微信错误动作和偏离固定文本的键盘输入。"""
        if name in ACTION_TOOLS:
            state["actions"] += 1
        text = str(arguments.get("text") or "")
        if (
            task.id == "terminal"
            and name in {"keyboard_type", "type_text"}
            and text.strip() != "whoami"
        ):
            state["violations"].append("terminal_command")
            return "基线评测已阻止：Terminal 仅允许固定无副作用命令"
        if task.id == "wechat":
            if name in {"mouse_click", "mouse_drag", "mouse_scroll"}:
                state["violations"].append("wechat_navigation")
                return "基线评测已阻止：微信任务不得点击、搜索或切换联系人"
            if name in {"keyboard_type", "type_text"} and text != "你好我是MAX":
                state["violations"].append("wechat_text")
                return "基线评测已阻止：微信仅允许发送指定文本你好我是MAX"
        if (
            task.id == "reminders"
            and name in {"keyboard_type", "type_text"}
            and text != "你好我是MAX"
        ):
            state["violations"].append("reminders_text")
            return "基线评测已阻止：提醒事项仅允许创建指定文本"
        return None

    guard.state = state  # type: ignore[attr-defined]
    return guard


def _status(state: dict[str, Any], guard: Callable[..., object]) -> BaselineStatus:
    """把 Agent 状态与护栏状态规范为基线执行终态。"""
    violations = guard.state["violations"]  # type: ignore[attr-defined]
    if violations:
        return BaselineStatus.VIOLATION
    status = str(state.get("status") or "error")
    if status == "done":
        return BaselineStatus.COMPLETED
    if status == "interrupted":
        return BaselineStatus.SAFETY_BLOCKED
    return BaselineStatus.AGENT_ERROR


def _last_screenshot(state: dict[str, Any]) -> Path | None:
    """从 Agent 消息逆序取得最后一张实际存在的工具截图。"""
    latest = (state.get("task_context") or {}).get("latest_observation")
    if isinstance(latest, dict):
        path = Path(str(latest.get("path") or ""))
        if path.is_file():
            return path
    for message in reversed(list(state.get("messages") or [])):
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, dict):
            continue
        for image in reversed(content.get("images") or []):
            path = Path(str(image.get("path"))) if isinstance(image, dict) else Path(str(image))
            if path.is_file():
                return path
    return None


async def _capture_terminal_screenshot(registry: Any) -> Path | None:
    """在执行终态后取得当前桌面截图，不依赖 Agent 是否返回状态。"""
    output = await registry.invoke("screenshot", {})
    if isinstance(output, ToolResult) and output.ok and output.images:
        path = Path(str(output.images[-1]))
        return path if path.is_file() else None
    return None


def _result(
    task: BaselineTask,
    round_id: str,
    nonce: str,
    status: BaselineStatus,
    started: float,
    session: Any,
    guard: Callable[..., object],
    final_path: Path | None,
    screenshot_source: str | None,
    detail: str,
    claimed: bool = False,
    review: Any = None,
) -> BaselineResult:
    """从会话汇总与评审结果构造单题指标。"""
    summary = session.run_summary or {}
    review_verdict = review.verdict if review else None
    success = not guard.state["violations"] and review_verdict is ReviewVerdict.PASS  # type: ignore[attr-defined]
    return BaselineResult(
        task.id,
        round_id,
        nonce,
        "baseline-desktop-v1",
        BaselineStatus.READY,
        status,
        review_verdict,
        review.error if review else None,
        claimed,
        success,
        int(summary.get("duration_ms") or 0) or None,
        review.duration_ms if review else None,
        int((time.perf_counter() - started) * 1000),
        int(summary.get("tool_calls") or 0),
        int(summary.get("tool_failures") or 0),
        int(guard.state["actions"]),  # type: ignore[attr-defined]
        tuple(guard.state["violations"]),  # type: ignore[attr-defined]
        summary.get("total_tokens"),
        review.total_tokens if review else None,
        str(final_path) if final_path else None,
        screenshot_source,
        _run_log_path(session),
        detail,
    )


def _run_log_path(session: Any) -> str | None:
    """从会话终态汇总导出当前运行 JSONL 引用。"""
    run_id = (session.run_summary or {}).get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return None
    return str(session_store_path(session, run_id))


def session_store_path(session: Any, run_id: str) -> Path:
    """保留运行日志路径组装的独立入口，便于测试替换。"""
    return Path("artifacts/runs") / f"{run_id}.jsonl"


def _blocked(
    task: BaselineTask,
    round_id: str,
    nonce: str,
    status: BaselineStatus,
    detail: str,
    started: float,
) -> BaselineResult:
    """构造未调用模型的环境或安全阻断结果。"""
    return BaselineResult(
        task.id,
        round_id,
        nonce,
        "baseline-desktop-v1",
        status,
        None,
        None,
        None,
        False,
        False,
        None,
        None,
        None,
        int((time.perf_counter() - started) * 1000),
        None,
        None,
        None,
        (),
        None,
        None,
        None,
        None,
        detail,
    )


def _notice(tasks: tuple[BaselineTask, ...], rounds: int, settings: Settings) -> str:
    """生成开始前确认文案，明确云端截图与重复写入边界。"""
    writes = sum(task.risk is RiskLevel.PERSONAL_WRITE for task in tasks) * rounds
    return f"将运行 {rounds} 轮 5 项真实桌面任务，含 {writes} 次个人写入。provider={settings.provider}；云端 provider 会接收最终截图。"


def _task_confirmation_notice(task: BaselineTask, round_id: str) -> str:
    """生成单题窗口前置确认文案，避免 Agent 在错误前台窗口开始动作。"""
    window = WINDOW_HINTS.get(task.id, task.id)
    preconditions = "；".join(task.preconditions)
    return f"[{round_id}/{task.id}] 请将 {window} 前置，并确认：{preconditions}。"


def _terminal_task_confirm(task: BaselineTask, round_id: str) -> bool:
    """在交互终端等待单键确认；Esc 跳过当前题，非 TTY 时退化为回车确认。

    参数：任务和轮次用于展示前台窗口提示。
    返回：除 Esc 外的任意按键返回真；Esc 返回假，以安全阻断当前题。
    异常：读取终端失败或用户中断时向调用方传播，避免静默执行桌面任务。
    """
    print(_task_confirmation_notice(task, round_id), flush=True)
    if not sys.stdin.isatty():
        input("按回车键继续：")
        return True
    print("按任意键继续，按 Esc 跳过本题：", end="", flush=True)
    descriptor = sys.stdin.fileno()
    original = termios.tcgetattr(descriptor)
    try:
        tty.setcbreak(descriptor)
        key = sys.stdin.read(1)
    finally:
        termios.tcsetattr(descriptor, termios.TCSADRAIN, original)
    print()
    return key != "\x1b"


def _terminal_confirm(notice: str) -> bool:
    """要求用户在交互终端输入固定确认词。"""
    print(notice)
    return input("输入 RUN_BASELINE 确认：").strip() == "RUN_BASELINE"
