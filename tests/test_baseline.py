"""真实桌面基线评测的任务契约、护栏、指标和可视化测试。"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from max_gui.baseline.comparison import (
    METRICS,
    _model_colors,
    _select_chinese_font,
    write_comparison_report,
)
from max_gui.baseline.environment import BaselineEnvironment
from max_gui.baseline.models import (
    BaselineResult,
    BaselineStatus,
    BaselineTask,
    ReviewVerdict,
    RiskLevel,
)
from max_gui.baseline.report import summarize, write_run_record
from max_gui.baseline.review import _parse, review_screenshot
from max_gui.baseline.scoring import SCORE_VERSION, calculate_score
from max_gui.baseline.service import (
    BASELINE_EXCLUDED_TOOLS,
    EXECUTION_TIMEOUT_SECONDS,
    MODEL_CALL_LIMIT,
    _BaselineConsoleTrace,
    _build_review_settings,
    _status,
    _task_confirmation_notice,
    run_baseline,
)
from max_gui.baseline.tasks import DEFAULT_TASKS, load_tasks
from max_gui.cli import build_parser, main
from max_gui.inference.client import ChatDelta
from max_gui.provider import PROVIDERS, MissingProviderKeyError


def _test_review_settings(settings: object) -> object:
    """基于执行夹具构造无需真实密钥的固定 Qiniu 评审配置。"""
    provider = PROVIDERS["qiniu"]
    return replace(
        settings,
        provider=provider.name,
        base_url=provider.base_url,
        api_key="test-qiniu-key",
        model_name=provider.model_name,
        context_window=provider.context_window,
        inference_max_retries=2,
        enable_thinking=True,
        reasoning_effort="low",
    )


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
    assert {task.timeout_seconds for task in tasks} == {EXECUTION_TIMEOUT_SECONDS}
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


def _scored_result(
    *,
    model_task: str = "calculator",
    preflight_status: BaselineStatus = BaselineStatus.READY,
    verdict: ReviewVerdict | None = ReviewVerdict.PASS,
    execution_duration_ms: int | None = 90_000,
    actions: int | None = 5,
    tool_calls: int | None = 3,
    tool_failures: int | None = 0,
    execution_tokens: int | None = 50_000,
) -> BaselineResult:
    """构造带当前评分结构的无副作用测试结果。"""
    score = calculate_score(
        timeout_seconds=300,
        preflight_status=preflight_status,
        review_verdict=verdict,
        review_error=None,
        has_screenshot=preflight_status is BaselineStatus.READY,
        execution_duration_ms=execution_duration_ms,
        actions=actions,
        tool_calls=tool_calls,
        tool_failures=tool_failures,
        execution_tokens=execution_tokens,
    )
    return BaselineResult(
        task_id=model_task,
        round_id="round-001",
        nonce="n",
        prompt_version="baseline-desktop-v1",
        preflight_status=preflight_status,
        execution_status=(
            BaselineStatus.COMPLETED if preflight_status is BaselineStatus.READY else None
        ),
        review_verdict=verdict,
        review_error=None,
        agent_claimed_complete=True,
        success=verdict is ReviewVerdict.PASS,
        execution_duration_ms=execution_duration_ms,
        review_duration_ms=20,
        total_duration_ms=(execution_duration_ms or 0) + 20,
        model_calls=4,
        tool_calls=tool_calls,
        tool_failures=tool_failures,
        actions=actions,
        execution_tokens=execution_tokens,
        review_tokens=123,
        final_screenshot="screen.png",
        screenshot_source="post_termination_snapshot",
        run_log="run.jsonl",
        score=score,
    )


def test_score_formula_boundaries_and_unknown_metrics() -> None:
    """评分覆盖正常值、参考上限和未知 Token，不包含 violation 硬门槛。"""
    normal = _scored_result().score
    assert normal and normal.version == SCORE_VERSION
    assert normal.total == 91.0
    assert normal.complete

    boundary = _scored_result(
        execution_duration_ms=300_000,
        actions=10,
        tool_calls=15,
        tool_failures=15,
        execution_tokens=100_000,
    ).score
    assert boundary and boundary.total == 70.0

    unknown = _scored_result(execution_tokens=None).score
    assert unknown and unknown.total is None and not unknown.complete
    assert unknown.missing_metrics == ("execution_tokens",)

    blocked = _scored_result(
        preflight_status=BaselineStatus.ENVIRONMENT_BLOCKED,
        verdict=None,
        execution_duration_ms=None,
        actions=None,
        tool_calls=None,
        tool_failures=None,
        execution_tokens=None,
    ).score
    assert blocked and blocked.total is None
    assert blocked.missing_metrics == ("not_measured",)


def test_summary_score_coverage_and_json_round_trip(tmp_path: Path) -> None:
    """完整批次写平均总分；存在无分题时保持空总分并保存覆盖率。"""
    complete = [_scored_result(), _scored_result(model_task="terminal")]
    complete_summary = summarize(complete)
    assert complete_summary["overall_score"] == 91.0
    assert complete_summary["score_coverage"] == 1.0
    assert complete_summary["score_version"] == SCORE_VERSION

    incomplete = [complete[0], _scored_result(execution_tokens=None)]
    incomplete_summary = summarize(incomplete)
    assert incomplete_summary["overall_score"] is None
    assert incomplete_summary["score_coverage"] == 0.5

    target = tmp_path / "baseline.json"
    write_run_record(target, {"model": "test-model"}, complete)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert "violations" not in payload["results"][0]
    assert "safety_violation" not in payload["results"][0]["score"]
    assert payload["results"][0]["score"]["version"] == SCORE_VERSION
    assert payload["results"][0]["score"]["references"]["timeout_ms"] == 300_000
    assert payload["results"][0]["model_calls"] == 4
    assert payload["summary"]["total_model_calls"] == 8
    assert payload["summary"]["overall_score"] == 91.0


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


def test_review_settings_are_fixed_to_qiniu_and_isolated(
    settings: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """统一评审读取 Qiniu 注册定义与专属密钥，且不修改执行配置。"""
    execution_provider = settings.provider
    execution_model = settings.model_name
    monkeypatch.setenv("MAX_QINIU_KEY", "judge-key")

    review_settings = _build_review_settings(settings)  # type: ignore[arg-type]
    provider = PROVIDERS["qiniu"]

    assert review_settings.provider == "qiniu"
    assert review_settings.model_name == provider.model_name
    assert review_settings.base_url == provider.base_url
    assert review_settings.context_window == provider.context_window
    assert review_settings.api_key == "judge-key"
    assert review_settings.inference_max_retries == 2
    assert review_settings.enable_thinking
    assert review_settings.reasoning_effort == "low"
    assert settings.provider == execution_provider
    assert settings.model_name == execution_model


def test_review_settings_require_qiniu_key(settings: object) -> None:
    """缺少统一评审密钥时在执行桌面任务前明确失败。"""
    with pytest.raises(MissingProviderKeyError, match="MAX_QINIU_KEY"):
        _build_review_settings(settings)  # type: ignore[arg-type]


def test_run_manifest_separates_execution_and_qiniu_review(
    settings: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """运行清单同时记录执行配置与固定 Qiniu 评审配置。"""
    from max_gui.baseline import service

    captured: dict[str, object] = {}

    async def fake_run_all(*_: object, **kwargs: object) -> list[BaselineResult]:
        """验证编排器把同一份 Qiniu 配置传给任务循环。"""
        review_settings = kwargs["review_settings"]
        assert review_settings.provider == "qiniu"
        return []

    def fake_write(_: Path, manifest: dict[str, object], __: list[BaselineResult]) -> None:
        """截获运行清单，避免测试写入真实评测记录。"""
        captured.update(manifest)

    monkeypatch.setenv("MAX_QINIU_KEY", "judge-key")
    monkeypatch.setattr(service, "_run_all", fake_run_all)
    monkeypatch.setattr(service, "write_run_record", fake_write)

    service.run_baseline(
        settings,  # type: ignore[arg-type]
        task_confirm=lambda *_: True,
    )

    assert captured["provider"] == settings.provider
    assert captured["model"] == settings.model_name
    assert captured["review_provider"] == "qiniu"
    assert captured["review_model"] == PROVIDERS["qiniu"].model_name
    output = capsys.readouterr().out
    assert "Baseline 执行模型" in output
    assert f"provider：{settings.provider}" in output
    assert f"model：{settings.model_name}" in output


def test_comparison_report_writes_markdown_charts_and_preserves_sources(tmp_path: Path) -> None:
    """两份当前记录生成固定表格和八张图，同名模型保持同色且源文件不变。"""
    try:
        _select_chinese_font()
    except ValueError:
        pytest.skip("当前测试主机未安装候选中文字体")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_run_record(first, {"model": "same-model"}, [_scored_result()])
    write_run_record(second, {"model": "same-model"}, [_scored_result(model_task="terminal")])
    before = {path: path.read_bytes() for path in (first, second)}

    directory = write_comparison_report([first, second], tmp_path / "reports")
    markdown = (directory / "report.md").read_text(encoding="utf-8")
    assert markdown.count("| same-model |") == 2
    assert "评审 Token" not in markdown
    assert "review_tokens" not in markdown
    assert str(first.resolve()) in markdown and str(second.resolve()) in markdown
    assert {path.name for path in directory.iterdir()} == {"report.md", "charts"}
    assert {path.name for path in (directory / "charts").iterdir()} == {
        metric.filename for metric in METRICS
    }
    assert all(path.read_bytes() == before[path] for path in (first, second))
    assert len(set(_model_colors(["same-model", "other-model"]).values())) == 2
    with pytest.raises(ValueError, match="1 至 5"):
        write_comparison_report([first] * 6, tmp_path / "reports")


def test_comparison_report_fails_before_output_without_chinese_font(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """没有候选中文字体时清晰失败，且不创建半成品报告目录。"""
    source = tmp_path / "run.json"
    write_run_record(source, {"model": "test-model"}, [_scored_result()])
    monkeypatch.setattr(
        "max_gui.baseline.comparison.PROJECT_CHINESE_FONT", tmp_path / "missing-font.ttf"
    )
    monkeypatch.setattr("max_gui.baseline.comparison.font_manager.fontManager.ttflist", [])
    output_root = tmp_path / "reports"
    with pytest.raises(ValueError, match="中文图表"):
        write_comparison_report([source], output_root)
    assert not output_root.exists()


def test_baseline_cli_does_not_generate_report_automatically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """普通 baseline 只调用执行入口并打印 JSON 路径，不触发报告模块。"""
    output = tmp_path / "result.json"
    settings = SimpleNamespace(project_root=tmp_path)
    monkeypatch.setattr("max_gui.cli.load_settings", lambda **_: settings)
    monkeypatch.setattr("max_gui.baseline.run_baseline", lambda *_args, **_kwargs: output)
    monkeypatch.setattr(
        "max_gui.baseline.comparison.write_comparison_report",
        lambda *_args, **_kwargs: pytest.fail("普通 baseline 不应调用报告入口"),
    )

    main(["--baseline"])

    assert f"基线评测结果已写入：{output}" in capsys.readouterr().out
    assert not (tmp_path / "artifacts" / "evaluations" / "baseline-desktop-reports").exists()


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

    async def fake_run(
        _: object, task: BaselineTask, *args: object, **_kwargs: object
    ) -> BaselineResult:
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
    results = await service._run_all(
        settings,  # type: ignore[arg-type]
        tasks,
        1,
        task_confirm,
        review_settings=_test_review_settings(settings),  # type: ignore[arg-type]
    )

    assert confirmed == [
        ("terminal", "round-001"),
        ("calculator", "round-001"),
        ("reminders", "round-001"),
    ]
    assert executed == ["terminal", "reminders"]
    calculator = next(result for result in results if result.task_id == "calculator")
    assert calculator.preflight_status is BaselineStatus.SAFETY_BLOCKED
    assert calculator.detail == "用户未确认所需窗口已前置"
    notice = _task_confirmation_notice(tasks[0], "round-001")
    assert "Terminal" in notice
    assert "最多执行 5 分钟" in notice
    assert "20 次" in notice
    assert "以先到者为准" in notice
    assert "开放除 activate_app、click 外的已注册工具" in notice
    assert "终态截图将发送至 Qiniu 评审" in notice


@pytest.mark.asyncio
async def test_execution_reviews_one_terminal_screenshot(
    settings: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """模拟 Agent 正文、工具和评审链路，验证顺序输出且不注册思考回调。"""
    from max_gui.baseline import service
    from max_gui.baseline.models import ReviewResult

    screenshot = tmp_path / "source.png"
    screenshot.write_bytes(b"png")
    agent_inputs: list[str] = []
    runner_settings: list[object] = []

    class FakeRunner:
        """提供最小完成状态，避免测试驱动真实桌面。"""

        def __init__(self, runner_settings_value: object, *_: object) -> None:
            """记录 baseline 专用 settings，验证模型调用额度。"""
            runner_settings.append(runner_settings_value)

        async def run(self, session: object, **kwargs: object) -> dict[str, object]:
            """回放正文和工具步骤，再模拟达到模型调用额度。"""
            from max_gui.agent.graph import ITERATION_LIMIT_MESSAGE

            agent_inputs.append(str(kwargs["user_text"]))
            assert "on_reasoning" not in kwargs
            assert "tool_guard" not in kwargs
            assert kwargs["expose_all_tools"] is True
            assert kwargs["excluded_tools"] == set(BASELINE_EXCLUDED_TOOLS)
            on_token = kwargs["on_token"]
            on_step = kwargs["on_evaluation_step"]
            assert callable(on_token) and callable(on_step)
            on_token("模型正文")
            on_step(
                {
                    "tool_name": "mouse_click",
                    "arguments": {"x": 12, "y": 34},
                    "images": [str(screenshot)],
                    "text": "点击完成",
                    "ok": True,
                    "code": "ok",
                    "reasoning": "NEVER_SHOW_REASONING_SENTINEL",
                }
            )
            session.run_summary = {
                "duration_ms": 4,
                "model_calls": 1,
                "tool_calls": 2,
                "tool_failures": 0,
            }
            return {
                "status": "error",
                "error": ITERATION_LIMIT_MESSAGE,
                "task_context": {
                    "completion_verified": False,
                    "latest_observation": {"path": str(screenshot)},
                },
            }

        def interrupt(self) -> None:
            """正常完成路径不应请求中断。"""
            pytest.fail("正常完成的 baseline 不应请求中断 Agent")

    review_settings: list[object] = []

    async def fake_review(_: object, review_config: object, **kwargs: object) -> ReviewResult:
        """记录评审配置，并通过真实 trace 回调模拟输入和原始输出。"""
        review_settings.append(review_config)
        on_trace = kwargs["on_trace"]
        assert callable(on_trace)
        on_trace(
            "input",
            {
                "provider": "local",
                "model": "judge-model",
                "prompt": "评审提示词",
                "image": str(screenshot),
            },
        )
        on_trace("output", {"text": '{"verdict":"pass"}'})
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

    task = BaselineTask(
        "calculator",
        "任务 {nonce}，日期 {run_date}",
        "r",
        ("x",),
        RiskLevel.READ_ONLY,
        EXECUTION_TIMEOUT_SECONDS,
    )
    monkeypatch.setattr("max_gui.baseline.environment.platform.system", lambda: "Darwin")
    env = BaselineEnvironment(allow_personal_write=True)
    result = await service._run_one(
        settings,  # type: ignore[arg-type]
        task,
        env,
        "round-001",
        "n",
        "2026-08-30",
        review_settings=_test_review_settings(settings),  # type: ignore[arg-type]
    )
    assert result.success
    assert result.execution_status is BaselineStatus.MODEL_LIMIT
    assert not result.agent_claimed_complete
    assert result.actions == 1
    assert result.model_calls == 1
    assert len(runner_settings) == 1
    assert runner_settings[0].max_iterations == MODEL_CALL_LIMIT
    assert len(review_settings) == 1
    assert review_settings[0].inference_max_retries == 2
    assert review_settings[0].provider == "qiniu"
    assert review_settings[0].model_name == PROVIDERS["qiniu"].model_name
    assert runner_settings[0].provider != review_settings[0].provider
    assert result.final_screenshot == str(screenshot)
    assert result.screenshot_source == "post_termination_snapshot"
    assert agent_inputs == ["任务 n，日期 2026-08-30"]
    output = capsys.readouterr().out
    assert output.index("Agent 提示词") < output.index("模型正文")
    assert output.index("模型正文") < output.index("工具步骤 1")
    assert output.index("工具步骤 1") < output.index("评审 AI 输入")
    assert output.index("评审 AI 输入") < output.index("评审 AI 输出")
    assert '参数：{"x": 12, "y": 34}' in output
    assert "点击完成" in output
    assert str(screenshot) not in output
    assert '"view_width"' not in output
    assert "截图：已截图" in output
    assert "NEVER_SHOW_REASONING_SENTINEL" not in output
    assert "reasoning" not in output
    result_json = json.dumps(result.to_dict(), ensure_ascii=False)
    assert "模型正文" not in result_json
    assert "任务 n，日期 2026-08-30" not in result_json
    assert "评审提示词" not in result_json
    assert "violations" not in result_json


@pytest.mark.asyncio
async def test_execution_timeout_interrupts_then_reviews(
    settings: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """300 秒执行时限先温和中断 Agent，并继续用终态截图调用评审。"""
    from max_gui.baseline import service
    from max_gui.baseline.models import ReviewResult
    from max_gui.tools.protocol import ToolResult

    screenshot = tmp_path / "timeout.png"
    screenshot.write_bytes(b"png")
    interrupted = asyncio.Event()
    review_calls = 0

    class TimeoutRunner:
        """等待编排器中断后持久化最小运行摘要。"""

        def __init__(self, *_: object) -> None:
            """接受生产构造参数。"""

        async def run(self, session: object, **_: object) -> dict[str, object]:
            """收到温和中断后返回 Agent 中断终态。"""
            await interrupted.wait()
            session.run_summary = {
                "duration_ms": 300_000,
                "model_calls": 2,
                "tool_calls": 1,
                "tool_failures": 0,
                "total_tokens": 20,
            }
            return {"status": "interrupted", "task_context": {}}

        def interrupt(self) -> None:
            """响应 300 秒时限并允许 Agent 温和收尾。"""
            interrupted.set()

    class FakeRegistry:
        """在执行超时后提供当前桌面截图。"""

        async def invoke(self, *_: object) -> ToolResult:
            """返回固定终态截图。"""
            return ToolResult(ok=True, text="截图成功", images=[str(screenshot)])

    async def fake_review(*_: object, **__: object) -> ReviewResult:
        """记录超时后评审调用并返回通过。"""
        nonlocal review_calls
        review_calls += 1
        return ReviewResult(ReviewVerdict.PASS, "可见", "完成", 1, None)

    monkeypatch.setattr(service, "AgentRunner", TimeoutRunner)
    monkeypatch.setattr(service, "build_default_registry", lambda *_args, **_kwargs: FakeRegistry())
    monkeypatch.setattr(service, "review_screenshot", fake_review)
    monkeypatch.setattr(service, "EXECUTION_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(service, "INTERRUPT_GRACE_SECONDS", 0.1)
    monkeypatch.setattr(service, "REVIEW_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr("max_gui.baseline.environment.platform.system", lambda: "Darwin")
    task = BaselineTask("calculator", "p", "r", ("x",), RiskLevel.READ_ONLY, 300)

    result = await service._run_one(
        settings,
        task,
        BaselineEnvironment(allow_personal_write=True),
        "round-001",
        "n",
        "2026-08-31",
        review_settings=_test_review_settings(settings),  # type: ignore[arg-type]
    )

    assert result.execution_status is BaselineStatus.TIMEOUT
    assert result.review_verdict is ReviewVerdict.PASS
    assert result.screenshot_source == "post_termination_snapshot"
    assert result.model_calls == 2
    assert review_calls == 1


@pytest.mark.asyncio
async def test_execution_timeout_forces_cancel_then_reviews(
    settings: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Agent 忽略温和中断时强制取消，但仍截取终态并调用评审。"""
    from max_gui.baseline import service
    from max_gui.baseline.models import ReviewResult
    from max_gui.tools.protocol import ToolResult

    screenshot = tmp_path / "timeout-forced.png"
    screenshot.write_bytes(b"png")
    review_calls = 0

    class StuckRunner:
        """模拟无法在温和中断窗口内自行退出的 Agent。"""

        def __init__(self, *_: object) -> None:
            """接受生产构造参数。"""

        async def run(self, *_: object, **__: object) -> dict[str, object]:
            """永久等待，直到编排器取消当前协程。"""
            await asyncio.Event().wait()
            return {}

        def interrupt(self) -> None:
            """故意忽略温和中断请求。"""

    class FakeRegistry:
        """在强制取消后提供当前桌面截图。"""

        async def invoke(self, *_: object) -> ToolResult:
            """返回固定终态截图。"""
            return ToolResult(ok=True, text="截图成功", images=[str(screenshot)])

    async def fake_review(*_: object, **__: object) -> ReviewResult:
        """记录强制取消后的评审调用。"""
        nonlocal review_calls
        review_calls += 1
        return ReviewResult(ReviewVerdict.FAIL, "不可见", "未完成", 1, None)

    monkeypatch.setattr(service, "AgentRunner", StuckRunner)
    monkeypatch.setattr(service, "build_default_registry", lambda *_args, **_kwargs: FakeRegistry())
    monkeypatch.setattr(service, "review_screenshot", fake_review)
    monkeypatch.setattr(service, "EXECUTION_TIMEOUT_SECONDS", 0.001)
    monkeypatch.setattr(service, "INTERRUPT_GRACE_SECONDS", 0.001)
    monkeypatch.setattr(service, "REVIEW_COOLDOWN_SECONDS", 0)
    monkeypatch.setattr("max_gui.baseline.environment.platform.system", lambda: "Darwin")
    task = BaselineTask("calculator", "p", "r", ("x",), RiskLevel.READ_ONLY, 300)

    result = await service._run_one(
        settings,
        task,
        BaselineEnvironment(allow_personal_write=True),
        "round-001",
        "n",
        "2026-08-31",
        review_settings=_test_review_settings(settings),  # type: ignore[arg-type]
    )

    assert result.execution_status is BaselineStatus.TIMEOUT_FORCED
    assert result.review_verdict is ReviewVerdict.FAIL
    assert result.screenshot_source == "post_termination_snapshot"
    assert review_calls == 1


def test_model_iteration_limit_maps_to_baseline_model_limit() -> None:
    """执行 Agent 的迭代上限错误映射为独立的模型调用额度终态。"""
    from max_gui.agent.graph import ITERATION_LIMIT_MESSAGE

    assert (
        _status({"status": "error", "error": ITERATION_LIMIT_MESSAGE}) is BaselineStatus.MODEL_LIMIT
    )


def test_console_trace_prints_tool_only_step_without_reasoning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """没有模型正文时仍打印工具步骤，并忽略回调中的思考字段。"""
    trace = _BaselineConsoleTrace("round-001", "calculator")
    trace.on_tool_step(
        {
            "tool_name": "screenshot",
            "arguments": {},
            "images": ["/private/sensitive/screenshot.png"],
            "text": '{"path":"/private/sensitive/screenshot.png","view_width":1280}',
            "ok": True,
            "code": "ok",
            "reasoning": "TOOL_ONLY_REASONING_SENTINEL",
        }
    )

    output = capsys.readouterr().out
    assert "模型输出" not in output
    assert "工具步骤 1" in output
    assert "工具：screenshot" in output
    assert "参数：" not in output
    assert "状态：成功（ok）" in output
    assert "结果：已截图" in output
    assert "/private/sensitive/screenshot.png" not in output
    assert '"view_width"' not in output
    assert "TOOL_ONLY_REASONING_SENTINEL" not in output
    assert "reasoning" not in output


@pytest.mark.asyncio
async def test_review_trace_reports_raw_invalid_output_before_parse_error(
    settings: object, tmp_path: Path
) -> None:
    """无效评审正文先原样回调，再回调解析错误且不包含图像编码。"""
    screenshot = tmp_path / "review.png"
    Image.new("RGB", (2, 2), "white").save(screenshot)
    events: list[tuple[str, dict[str, str]]] = []

    class FakeClient:
        """返回固定无效正文的无网络评审客户端。"""

        async def stream(self, *_: object, **__: object) -> ChatDelta:
            """返回不符合 JSON 契约的原始模型正文。"""
            return ChatDelta(text="INVALID_RAW_REVIEW_OUTPUT")

    result = await review_screenshot(
        FakeClient(),  # type: ignore[arg-type]
        settings,  # type: ignore[arg-type]
        rubric="截图必须显示 2",
        image=screenshot,
        run_date="2026-08-31",
        on_trace=lambda kind, payload: events.append((kind, payload)),
    )

    assert not result.verdict
    assert [kind for kind, _ in events] == ["input", "output", "error"]
    assert events[1][1]["text"] == "INVALID_RAW_REVIEW_OUTPUT"
    assert events[0][1]["image"] == str(screenshot)
    assert "截图必须显示 2" in events[0][1]["prompt"]
    assert "base64" not in json.dumps(events, ensure_ascii=False)
    assert "data:image" not in json.dumps(events, ensure_ascii=False)


@pytest.mark.asyncio
async def test_review_trace_redacts_credentials_from_service_error(
    settings: object, tmp_path: Path
) -> None:
    """评审调用失败只回调凭据遮蔽后的安全错误摘要。"""
    screenshot = tmp_path / "review.png"
    Image.new("RGB", (2, 2), "white").save(screenshot)
    events: list[tuple[str, dict[str, str]]] = []
    secret_settings = replace(settings, api_key="do-not-print")  # type: ignore[arg-type]

    class FailingClient:
        """抛出带常见认证字段的无网络评审客户端。"""

        async def stream(self, *_: object, **__: object) -> ChatDelta:
            """模拟包含 API Key 与 Bearer 值的 provider 错误。"""
            raise RuntimeError("api_key=secret-value Authorization: Bearer bearer-value")

    result = await review_screenshot(
        FailingClient(),  # type: ignore[arg-type]
        secret_settings,
        rubric="规则",
        image=screenshot,
        run_date="2026-08-31",
        on_trace=lambda kind, payload: events.append((kind, payload)),
    )

    rendered = json.dumps(events, ensure_ascii=False)
    assert result.error
    assert [kind for kind, _ in events] == ["input", "error"]
    assert "secret-value" not in rendered
    assert "bearer-value" not in rendered
    assert "do-not-print" not in rendered
    assert "***" in rendered
