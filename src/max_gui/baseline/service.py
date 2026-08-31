"""五题真实桌面基线评测的顺序编排入口。"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import sys
import termios
import time
import tty
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from max_gui.agent.graph import ITERATION_LIMIT_MESSAGE, AgentRunner
from max_gui.baseline.environment import BaselineEnvironment
from max_gui.baseline.models import (
    BaselineResult,
    BaselineStatus,
    BaselineTask,
    ReviewVerdict,
    RiskLevel,
)
from max_gui.baseline.report import write_run_record
from max_gui.baseline.review import ReviewTraceKind, review_screenshot
from max_gui.baseline.scoring import calculate_score
from max_gui.baseline.tasks import DEFAULT_TASKS, load_tasks
from max_gui.config import Settings
from max_gui.inference.client import InferenceClient
from max_gui.inference.retry import safe_retry_detail
from max_gui.provider import get_provider, require_provider_key
from max_gui.session.store import SessionStore
from max_gui.tools.protocol import ToolResult
from max_gui.tools.registry import AutoApproveGate, build_default_registry

REVIEW_COOLDOWN_SECONDS = 60
EXECUTION_TIMEOUT_SECONDS = 300
INTERRUPT_GRACE_SECONDS = 5
MODEL_CALL_LIMIT = 20
REVIEW_PROVIDER = "qiniu"
BASELINE_EXCLUDED_TOOLS = frozenset({"activate_app", "click"})

ACTION_TOOLS = frozenset(
    {
        "mouse_click",
        "mouse_drag",
        "mouse_move",
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


class _BaselineConsoleTrace:
    """把 baseline 调用链投影到终端，并从数据源排除模型思考字段。"""

    def __init__(self, round_id: str, task_id: str) -> None:
        """保存任务标签、工具序号与模型正文区块状态。"""
        self.label = f"{round_id}/{task_id}"
        self.tool_step = 0
        self.action_count = 0
        self.model_output_open = False

    def print_prompt(self, prompt: str) -> None:
        """打印将原样发送给 Agent 的任务提示词。"""
        self.finish_model_output()
        print(f"[{self.label}] Agent 提示词：", flush=True)
        print(prompt, flush=True)

    def on_token(self, token: str) -> None:
        """流式打印模型正文；该入口不会接收 reasoning 增量。"""
        if not token:
            return
        if not self.model_output_open:
            print(f"[{self.label}] 模型输出：", flush=True)
            self.model_output_open = True
        print(token, end="", flush=True)

    def on_tool_step(self, payload: dict[str, Any]) -> None:
        """仅打印可读的工具摘要，隐藏截图路径及其坐标元数据。"""
        self.finish_model_output()
        self.tool_step += 1
        tool_name = str(payload.get("tool_name") or "unknown")
        if tool_name in ACTION_TOOLS:
            self.action_count += 1
        arguments = payload.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        images = payload.get("images")
        if not isinstance(images, list):
            images = []
        status = "成功" if payload.get("ok") is True else "失败"
        code = str(payload.get("code") or "unknown")
        result = safe_retry_detail(payload.get("text") or "")
        print(f"[{self.label}] 工具步骤 {self.tool_step}：", flush=True)
        print(f"工具：{tool_name}", flush=True)
        if tool_name != "screenshot":
            print(
                "参数：" + json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str),
                flush=True,
            )
        print(f"状态：{status}（{code}）", flush=True)
        print(f"结果：{_without_screenshot_metadata(result, has_images=bool(images))}", flush=True)
        print("截图：已截图" if images else "截图：无", flush=True)

    def on_review_trace(self, kind: ReviewTraceKind, payload: dict[str, str]) -> None:
        """打印评审文本输入、原始输出或已遮蔽的错误摘要。"""
        self.finish_model_output()
        if kind == "input":
            print(f"[{self.label}] 评审 AI 输入：", flush=True)
            print(f"provider：{payload.get('provider', '')}", flush=True)
            print(f"model：{payload.get('model', '')}", flush=True)
            print("截图：已截图", flush=True)
            print(payload.get("prompt", ""), flush=True)
        elif kind == "output":
            print(f"[{self.label}] 评审 AI 输出：", flush=True)
            print(payload.get("text", ""), flush=True)
        else:
            print(f"[{self.label}] 评审 AI 错误：{payload.get('error', '')}", flush=True)

    def finish_model_output(self) -> None:
        """在流式正文区块结束时补换行，保持后续步骤可读。"""
        if not self.model_output_open:
            return
        print(flush=True)
        self.model_output_open = False


def _without_screenshot_metadata(result: str, *, has_images: bool) -> str:
    """移除工具文本中附带的截图 JSON，避免在终端泄露路径与坐标参数。

    参数：
        result：工具原始结果摘要。
        has_images：本步骤是否确实附带截图。

    返回：保留动作说明的简短结果；纯截图结果替换为“已截图”。
    """
    visible_lines: list[str] = []
    for line in result.splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            visible_lines.append(line)
            continue
        if not isinstance(value, dict) or "path" not in value:
            visible_lines.append(line)
    visible = "\n".join(visible_lines).strip()
    return visible or ("已截图" if has_images else result)


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
    异常：轮次数非正或任务契约无效时抛出 `ValueError`；缺少 Qiniu 评审密钥时抛出
    `MissingProviderKeyError`。
    """
    if rounds <= 0:
        raise ValueError("基线评测轮次数必须为正整数")
    tasks, digest = load_tasks(tasks_path)
    if task_confirm is None:
        task_confirm = _terminal_task_confirm
    print("Baseline 执行模型：", flush=True)
    print(f"provider：{settings.provider}", flush=True)
    print(f"model：{settings.model_name}", flush=True)
    review_settings = _build_review_settings(settings)
    batch_id = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    root = settings.project_root / "artifacts" / "evaluations" / "baseline-desktop"
    root.mkdir(parents=True, exist_ok=True)
    output = root / f"{batch_id}.json"
    if output.exists():
        output = root / f"{batch_id}-{uuid4().hex[:6]}.json"
    results = asyncio.run(
        _run_all(
            settings,
            tasks,
            rounds,
            task_confirm,
            review_settings=review_settings,
        )
    )
    write_run_record(
        output,
        {
            "batch_id": batch_id,
            "task_file": str(tasks_path.resolve()),
            "task_sha256": digest,
            "provider": settings.provider,
            "model": settings.model_name,
            "review_provider": review_settings.provider,
            "review_model": review_settings.model_name,
            "rounds": rounds,
            "model_call_limit": MODEL_CALL_LIMIT,
            "execution_timeout_seconds": EXECUTION_TIMEOUT_SECONDS,
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
    *,
    review_settings: Settings,
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
                result = await _run_one(
                    settings,
                    task,
                    environment,
                    round_id,
                    nonce,
                    run_date,
                    review_settings=review_settings,
                )
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
    *,
    review_settings: Settings,
) -> BaselineResult:
    """执行单题直至完成、达到五分钟或模型调用上限，再进行独立评审。"""
    started = time.perf_counter()
    preflight, detail = environment.preflight(task)
    if preflight is not BaselineStatus.READY:
        return _blocked(task, round_id, nonce, preflight, detail, started)
    environment.mark_write(task)
    events: list[Any] = []
    store = SessionStore(settings.sessions_dir)
    registry = build_default_registry(settings, gate=AutoApproveGate())
    retry_settings = replace(
        settings,
        inference_max_retries=2,
        max_iterations=MODEL_CALL_LIMIT,
    )
    runner = AgentRunner(retry_settings, InferenceClient(retry_settings), registry, store)
    session = store.create(model=settings.model_name, title=f"基线：{task.id}")
    console = _BaselineConsoleTrace(round_id, task.id)
    state: dict[str, Any] = {}
    status = BaselineStatus.AGENT_ERROR
    detail = ""
    agent_prompt = task.render_prompt(nonce, run_date)
    console.print_prompt(agent_prompt)
    agent_task = asyncio.create_task(
        runner.run(
            session,
            user_text=agent_prompt,
            on_token=console.on_token,
            on_event=events.append,
            on_evaluation_step=console.on_tool_step,
            expose_all_tools=True,
            excluded_tools=set(BASELINE_EXCLUDED_TOOLS),
        )
    )
    try:
        state = await asyncio.wait_for(
            asyncio.shield(agent_task), timeout=EXECUTION_TIMEOUT_SECONDS
        )
        status = _status(state)
    except TimeoutError:
        runner.interrupt()
        try:
            state = await asyncio.wait_for(
                asyncio.shield(agent_task), timeout=INTERRUPT_GRACE_SECONDS
            )
            status = BaselineStatus.TIMEOUT
            detail = "执行达到 5 分钟时限，Agent 已温和中断"
        except TimeoutError:
            agent_task.cancel()
            with suppress(asyncio.CancelledError):
                await agent_task
            status = BaselineStatus.TIMEOUT_FORCED
            detail = "执行达到 5 分钟时限，Agent 收尾超时后已强制取消"
        except Exception as exc:
            status = BaselineStatus.TIMEOUT
            detail = f"执行达到 5 分钟时限，Agent 收尾失败：{safe_retry_detail(exc)}"
    except Exception as exc:
        detail = f"LLM 调用失败：{safe_retry_detail(exc)}"
    console.finish_model_output()
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
        review = await review_screenshot(
            InferenceClient(review_settings),
            review_settings,
            rubric=task.render_rubric(nonce, run_date),
            image=screenshot,
            run_date=run_date,
            on_trace=console.on_review_trace,
        )
    return _result(
        task,
        round_id,
        nonce,
        status,
        started,
        session,
        console.action_count,
        screenshot,
        screenshot_source,
        detail,
        claimed,
        review,
    )


def _build_review_settings(settings: Settings) -> Settings:
    """构造固定 Qiniu 评审配置，同时保持执行配置不变。

    参数：`settings` 是执行 Agent 使用的配置，仅复用路径、图像和上下文预算等通用字段。
    返回：provider、模型、端点、密钥和上下文窗口均来自 Qiniu 注册定义，并为强制思考模型固定
    `reasoning_effort=low` 的独立配置。
    异常：未设置有效 `MAX_QINIU_KEY` 时抛出 `MissingProviderKeyError`。
    副作用：只读取进程环境变量，不修改传入配置或环境。
    """
    provider = get_provider(REVIEW_PROVIDER)
    key_name = provider.api_key_env or ""
    api_key = (os.environ.get(key_name) or "").strip()
    require_provider_key(provider, api_key)
    return replace(
        settings,
        provider=provider.name,
        base_url=provider.base_url,
        api_key=api_key,
        model_name=provider.model_name,
        context_window=provider.context_window,
        inference_max_retries=2,
        enable_thinking=True,
        reasoning_effort="low",
    )


def _announce_result(result: BaselineResult) -> None:
    """在独立截图评审完成后输出当前题的成功或失败结论。"""
    verdict = "成功" if result.success else "失败"
    reason = result.detail or str(result.execution_status or result.preflight_status)
    print(f"[{result.round_id}/{result.task_id}] 结果：{verdict}（{reason}）")


def _status(state: dict[str, Any]) -> BaselineStatus:
    """把 Agent 状态规范为 baseline 执行终态。"""
    status = str(state.get("status") or "error")
    if status == "done":
        return BaselineStatus.COMPLETED
    if status == "interrupted":
        return BaselineStatus.SAFETY_BLOCKED
    if state.get("error") == ITERATION_LIMIT_MESSAGE:
        return BaselineStatus.MODEL_LIMIT
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
    actions: int,
    final_path: Path | None,
    screenshot_source: str | None,
    detail: str,
    claimed: bool = False,
    review: Any = None,
) -> BaselineResult:
    """从会话汇总与评审结果构造单题指标。"""
    summary = session.run_summary or {}
    review_verdict = review.verdict if review else None
    success = review_verdict is ReviewVerdict.PASS
    execution_duration_ms = _optional_metric(summary.get("duration_ms"))
    model_calls = _optional_metric(summary.get("model_calls"))
    tool_calls = _optional_metric(summary.get("tool_calls"))
    tool_failures = _optional_metric(summary.get("tool_failures"))
    execution_tokens = _optional_metric(summary.get("total_tokens"))
    score = calculate_score(
        timeout_seconds=task.timeout_seconds,
        preflight_status=BaselineStatus.READY,
        review_verdict=review_verdict,
        review_error=review.error if review else None,
        has_screenshot=final_path is not None,
        execution_duration_ms=execution_duration_ms,
        actions=actions,
        tool_calls=tool_calls,
        tool_failures=tool_failures,
        execution_tokens=execution_tokens,
    )
    return BaselineResult(
        task_id=task.id,
        round_id=round_id,
        nonce=nonce,
        prompt_version="baseline-desktop-v1",
        preflight_status=BaselineStatus.READY,
        execution_status=status,
        review_verdict=review_verdict,
        review_error=review.error if review else None,
        agent_claimed_complete=claimed,
        success=success,
        execution_duration_ms=execution_duration_ms,
        review_duration_ms=review.duration_ms if review else None,
        total_duration_ms=int((time.perf_counter() - started) * 1000),
        model_calls=model_calls,
        tool_calls=tool_calls,
        tool_failures=tool_failures,
        actions=actions,
        execution_tokens=execution_tokens,
        review_tokens=review.total_tokens if review else None,
        final_screenshot=str(final_path) if final_path else None,
        screenshot_source=screenshot_source,
        run_log=_run_log_path(session),
        detail=detail,
        score=score,
    )


def _optional_metric(value: object) -> int | None:
    """把会话汇总中的非负数值规范为整数，缺失或非法值保持未知。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(value)


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
    score = calculate_score(
        timeout_seconds=task.timeout_seconds,
        preflight_status=status,
        review_verdict=None,
        review_error=None,
        has_screenshot=False,
        execution_duration_ms=None,
        actions=None,
        tool_calls=None,
        tool_failures=None,
        execution_tokens=None,
    )
    return BaselineResult(
        task_id=task.id,
        round_id=round_id,
        nonce=nonce,
        prompt_version="baseline-desktop-v1",
        preflight_status=status,
        execution_status=None,
        review_verdict=None,
        review_error=None,
        agent_claimed_complete=False,
        success=False,
        execution_duration_ms=None,
        review_duration_ms=None,
        total_duration_ms=int((time.perf_counter() - started) * 1000),
        model_calls=None,
        tool_calls=None,
        tool_failures=None,
        actions=None,
        execution_tokens=None,
        review_tokens=None,
        final_screenshot=None,
        screenshot_source=None,
        run_log=None,
        detail=detail,
        score=score,
    )


def _notice(tasks: tuple[BaselineTask, ...], rounds: int, settings: Settings) -> str:
    """生成开始前确认文案，明确云端截图与重复写入边界。"""
    writes = sum(task.risk is RiskLevel.PERSONAL_WRITE for task in tasks) * rounds
    return f"将运行 {rounds} 轮 5 项真实桌面任务，含 {writes} 次个人写入。provider={settings.provider}；云端 provider 会接收最终截图。"


def _task_confirmation_notice(task: BaselineTask, round_id: str) -> str:
    """生成单题窗口前置确认文案，避免 Agent 在错误前台窗口开始动作。"""
    window = WINDOW_HINTS.get(task.id, task.id)
    preconditions = "；".join(task.preconditions)
    return (
        f"[{round_id}/{task.id}] 请将 {window} 前置，并确认：{preconditions}。"
        f"本题最多执行 {EXECUTION_TIMEOUT_SECONDS // 60} 分钟或调用执行模型 "
        f"{MODEL_CALL_LIMIT} 次，以先到者为准，并开放除 activate_app、click 外的已注册工具。"
        "终态截图将发送至 Qiniu 评审。"
    )


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
