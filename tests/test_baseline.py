"""真实桌面基线评测的任务契约、护栏、指标和可视化测试。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from max_gui.baseline.comparison import write_comparison_report
from max_gui.baseline.environment import BaselineEnvironment
from max_gui.baseline.models import (
    BaselineResult,
    BaselineStatus,
    BaselineTask,
    ReviewVerdict,
    RiskLevel,
)
from max_gui.baseline.report import summarize, write_run_record, write_run_report
from max_gui.baseline.review import _parse
from max_gui.baseline.service import _guard, _task_confirmation_notice, run_baseline
from max_gui.baseline.tasks import DEFAULT_TASKS, load_tasks
from max_gui.cli import build_parser


def test_load_tasks_has_fixed_order_and_digest() -> None:
    """正式任务文件恰好提供五题、风险分类和稳定摘要。"""
    tasks, digest = load_tasks()
    assert [task.id for task in tasks] == [
        "weather",
        "terminal",
        "calculator",
        "reminders",
        "wechat",
    ]
    assert len(digest) == 64
    assert tasks[-1].risk is RiskLevel.PERSONAL_WRITE
    tasks_by_id = {task.id: task for task in tasks}
    assert "whoami" in tasks_by_id["terminal"].prompt
    assert "flkbme" in tasks_by_id["terminal"].review_rubric
    assert "你好我是MAX" in tasks_by_id["reminders"].prompt
    assert "你好我是MAX" in tasks_by_id["wechat"].review_rubric


def test_load_tasks_rejects_missing_or_duplicate_contract(tmp_path: Path) -> None:
    """任务文件缺失或重复 ID 时拒绝，避免实际桌面执行未知配置。"""
    with pytest.raises(ValueError, match="未找到"):
        load_tasks(tmp_path / "missing.json")
    payload = json.loads(DEFAULT_TASKS.read_text(encoding="utf-8"))
    payload["tasks"][1]["id"] = "weather"
    source = tmp_path / "bad.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError):
        load_tasks(source)


def test_wechat_guard_only_allows_fixed_text_without_navigation() -> None:
    """微信任务不允许模型点击、搜索或输入指定文本以外的内容。"""
    task = BaselineTask("wechat", "p", "r", ("x",), RiskLevel.PERSONAL_WRITE, 180)
    guard = _guard(task, "nonce")
    assert guard("mouse_click", {}) is not None
    assert guard("keyboard_type", {"text": "其它文本"}) is not None
    fresh = _guard(task, "nonce")
    assert fresh("keyboard_type", {"text": "你好我是MAX"}) is None
    assert fresh("type_text", {"text": "你好我是MAX"}) is None
    assert fresh("keyboard_press", {"keys": ["enter"]}) is None


def test_terminal_and_reminders_guards_only_allow_configured_text() -> None:
    """终端与提醒事项任务拒绝偏离固定验收内容的文本输入。"""
    terminal = BaselineTask("terminal", "p", "r", ("x",), RiskLevel.READ_ONLY, 180)
    reminders = BaselineTask("reminders", "p", "r", ("x",), RiskLevel.PERSONAL_WRITE, 180)

    assert _guard(terminal, "nonce")("keyboard_type", {"text": "pwd"}) is not None
    assert _guard(terminal, "nonce")("keyboard_type", {"text": "whoami"}) is None
    assert _guard(reminders, "nonce")("type_text", {"text": "其它提醒"}) is not None
    assert _guard(reminders, "nonce")("type_text", {"text": "你好我是MAX"}) is None


def test_environment_only_requires_platform_and_personal_write_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预检不读取应用路径，仅保留平台与个人写入预算边界。"""
    monkeypatch.setattr("max_gui.baseline.environment.platform.system", lambda: "Darwin")
    task = BaselineTask("reminders", "p", "r", ("x",), RiskLevel.PERSONAL_WRITE, 180)
    blocked = BaselineEnvironment()
    assert blocked.preflight(task)[0] is BaselineStatus.SAFETY_BLOCKED
    allowed = BaselineEnvironment(allow_personal_write=True)
    assert allowed.preflight(task)[0] is BaselineStatus.READY
    allowed.mark_write(task)
    assert allowed.preflight(task)[0] is BaselineStatus.SAFETY_BLOCKED


def test_review_parser_requires_exact_three_fields() -> None:
    """截图评审不能接受 Markdown 或附带自述字段。"""
    assert _parse('{"verdict":"pass","visible_evidence":"2","reason":"可见"}')["verdict"] == "pass"
    with pytest.raises(ValueError):
        _parse('{"verdict":"pass","reason":"x"}')


def test_report_preserves_unknown_metrics_and_writes_dashboard(tmp_path: Path) -> None:
    """未知 Token 不转零，dashboard 可离线读取样本数和 SVG。"""
    result = BaselineResult(
        "calculator",
        "round-001",
        "n",
        "baseline-desktop-v1",
        BaselineStatus.READY,
        BaselineStatus.COMPLETED,
        ReviewVerdict.PASS,
        None,
        True,
        True,
        100,
        None,
        100,
        3,
        0,
        3,
        (),
        None,
        None,
        None,
        None,
        None,
    )
    summary = summarize([result])
    assert summary["known_execution_tokens"] is None
    target = tmp_path / "baseline.json"
    write_run_record(target, {"model": "test"}, [result])
    assert target.is_file()
    report = write_run_report(target, tmp_path / "reports")
    assert "<svg" in (report / "dashboard.html").read_text(encoding="utf-8")
    assert (report / "success-rate.png").is_file()


def test_cli_accepts_baseline_and_keeps_benchmark_flag() -> None:
    """CLI 同时保留原 Web benchmark 与新基线入口。"""
    parsed = build_parser().parse_args(["--baseline", "--baseline-runs", "2"])
    assert parsed.baseline and parsed.baseline_runs == 2
    assert build_parser().parse_args(["--baseline", "-report", "one.json"]).baseline_report == [
        Path("one.json")
    ]
    assert build_parser().parse_args(["--baseline", "-clean"]).baseline_clean
    assert build_parser().parse_args(["--benchmark"]).benchmark


def test_run_baseline_rejects_invalid_rounds_before_task_confirmation(settings: object) -> None:
    """非法轮次数不会触发单题确认或任何真实桌面副作用。"""
    with pytest.raises(ValueError, match="正整数"):
        run_baseline(settings, rounds=0, task_confirm=lambda *_: True)  # type: ignore[arg-type]


def test_comparison_report_writes_png_and_rejects_more_than_five(tmp_path: Path) -> None:
    """JSON 对比报告输出两张图表，且输入数量严格限制为五份。"""
    summary = {"measured_tasks": 1, "success_rate": 1.0, "results": [{"execution_duration_ms": 12}]}
    source = tmp_path / "summary.json"
    source.write_text(json.dumps(summary), encoding="utf-8")
    directory = write_comparison_report([source], tmp_path / "reports")
    assert (directory / "success-rate.png").is_file()
    assert (directory / "execution-duration.png").is_file()
    with pytest.raises(ValueError, match="1 至 5"):
        write_comparison_report([source] * 6, tmp_path / "reports")


@pytest.mark.asyncio
async def test_each_task_waits_for_window_confirmation_before_agent(
    settings: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """每题均先确认前台窗口，拒绝时仅阻断该题且不创建 Agent。"""
    from max_gui.baseline import service

    tasks = (
        BaselineTask("terminal", "p", "r", ("Terminal 可启动",), RiskLevel.READ_ONLY, 180),
        BaselineTask("calculator", "p", "r", ("Calculator 可启动",), RiskLevel.READ_ONLY, 180),
        BaselineTask("reminders", "p", "r", ("Reminders 可启动",), RiskLevel.PERSONAL_WRITE, 180),
    )
    confirmed: list[tuple[str, str]] = []
    executed: list[str] = []

    def task_confirm(task: BaselineTask, round_id: str) -> bool:
        """记录确认顺序，并拒绝计算器题以验证不会启动 Agent。"""
        confirmed.append((task.id, round_id))
        return task.id != "calculator"

    async def fake_run(_: object, task: BaselineTask, *args: object) -> BaselineResult:
        """模拟 Agent 运行，仅记录真正进入执行阶段的任务。"""
        executed.append(task.id)
        return service._blocked(
            task,
            "round-001",
            "nonce",
            BaselineStatus.ENVIRONMENT_BLOCKED,
            "fake",
            time.perf_counter(),
        )

    monkeypatch.setattr(service, "_run_one", fake_run)
    results = await service._run_all(settings, tasks, 1, task_confirm)  # type: ignore[arg-type]

    assert confirmed == [
        ("terminal", "round-001"),
        ("calculator", "round-001"),
        ("reminders", "round-001"),
    ]
    assert executed == ["terminal", "reminders"]
    calculator = next(result for result in results if result.task_id == "calculator")
    assert calculator.preflight_status is BaselineStatus.SAFETY_BLOCKED
    assert calculator.detail == "用户未确认所需窗口已前置"
    assert "Terminal" in _task_confirmation_notice(tasks[0], "round-001")


@pytest.mark.asyncio
async def test_execution_reviews_one_terminal_screenshot(
    settings: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模拟 Agent 仅产出一次最终截图时，运行器只评审一次并写入证据副本。"""
    from max_gui.baseline import service
    from max_gui.baseline.models import ReviewResult

    screenshot = tmp_path / "source.png"
    screenshot.write_bytes(b"png")

    class FakeRunner:
        """提供最小完成状态，避免测试驱动真实桌面。"""

        def __init__(self, *_: object) -> None:
            """接受生产构造参数。"""

        async def run(self, session: object, **_: object) -> dict[str, object]:
            """写入可审计汇总并返回含最终观察的完成状态。"""
            session.run_summary = {"duration_ms": 4, "tool_calls": 2, "tool_failures": 0}
            return {
                "status": "done",
                "task_context": {
                    "completion_verified": False,
                    "latest_observation": {"path": str(screenshot)},
                },
            }

        def interrupt(self) -> None:
            """满足超时分支接口。"""

    review_settings: list[object] = []

    async def fake_review(_: object, review_config: object, **__: object) -> ReviewResult:
        """记录评审重试配置并返回通过。"""
        review_settings.append(review_config)
        return ReviewResult(ReviewVerdict.PASS, "2", "可见", 3, None)

    monkeypatch.setattr(service, "AgentRunner", FakeRunner)
    monkeypatch.setattr(service, "review_screenshot", fake_review)

    class FakeRegistry:
        """提供只读终态截图。"""

        async def invoke(self, *_: object) -> object:
            """返回当前截图。"""
            from max_gui.tools.protocol import ToolResult

            return ToolResult(ok=True, text="截图成功", images=[str(screenshot)])

    monkeypatch.setattr(service, "build_default_registry", lambda *_args, **_kwargs: FakeRegistry())
    monkeypatch.setattr(service, "REVIEW_COOLDOWN_SECONDS", 0)
    task = BaselineTask("calculator", "p", "r", ("x",), RiskLevel.READ_ONLY, 180)
    monkeypatch.setattr("max_gui.baseline.environment.platform.system", lambda: "Darwin")
    env = BaselineEnvironment(allow_personal_write=True)
    result = await service._run_one(settings, task, env, "round-001", "n", "2026-08-30")
    assert result.success
    assert not result.agent_claimed_complete
    assert len(review_settings) == 1
    assert review_settings[0].inference_max_retries == 2
    assert result.final_screenshot == str(screenshot)
    assert result.screenshot_source == "post_termination_snapshot"
