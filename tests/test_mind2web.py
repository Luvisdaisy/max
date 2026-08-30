"""Online-Mind2Web 契约测试：本地加载、安全阻断、轨迹和评测器边界。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from max_gui.mind2web.browser import IsolatedChrome, UrlObserver
from max_gui.mind2web.models import (
    EvaluationSummary,
    OnlineMind2WebTask,
    PreflightStatus,
    SafetyManifest,
    SafetyRule,
    TaskMetrics,
)
from max_gui.mind2web.preflight import RuntimeSafetyGuard, plan_preflight
from max_gui.mind2web.tasks import load_tasks
from max_gui.mind2web.trajectory import (
    EvaluationStepRecorder,
    TrajectoryValidationError,
    validate_v2,
)
from max_gui.mind2web.webjudge import WebJudgeError, run_webjudge


def _task() -> OnlineMind2WebTask:
    """构造一题无外部网络依赖的已授权任务。"""
    return OnlineMind2WebTask("sample", "https://example.com", "Read the page", 2)


def _rule() -> SafetyRule:
    """构造只读任务的最小域名与输入白名单。"""
    return SafetyRule("sample", ("example.com",), 8, 20, ("search",))


def test_load_tasks_is_local_strict_and_hashed(tmp_path: Path) -> None:
    """加载器只读取授权根内 JSON，并拒绝重复 ID。"""
    source = tmp_path / "tasks.json"
    source.write_text(
        json.dumps(
            [
                {
                    "task_id": "a",
                    "website": "https://example.com",
                    "task_description": "x",
                    "reference_length": 1,
                }
            ]
        ),
        encoding="utf-8",
    )
    tasks, digest = load_tasks(source, authorized_root=tmp_path)
    assert tasks[0].task_id == "a"
    assert len(digest) == 64
    source.write_text(
        json.dumps(
            [
                {
                    "task_id": "a",
                    "website": "https://example.com",
                    "instruction": "x",
                    "reference_length": 1,
                }
            ]
            * 2
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="重复"):
        load_tasks(source, authorized_root=tmp_path)


def test_load_tasks_accepts_upstream_confirmed_task(tmp_path: Path) -> None:
    """上游公开数据实际使用 confirmed_task 字段，加载器应保持兼容。"""
    source = tmp_path / "tasks.json"
    source.write_text(
        json.dumps(
            [
                {
                    "task_id": "confirmed",
                    "website": "https://example.com",
                    "confirmed_task": "Read the page",
                    "reference_length": 1,
                }
            ]
        ),
        encoding="utf-8",
    )
    tasks, _ = load_tasks(source, authorized_root=tmp_path)
    assert tasks[0].instruction == "Read the page"


def test_manifest_preflight_and_runtime_guard() -> None:
    """未授权任务、越域和敏感输入均被安全边界阻断。"""
    task, rule = _task(), _rule()
    manifest = SafetyManifest("test", (rule,))
    assert plan_preflight(task, manifest).status is PreflightStatus.READY
    guard = RuntimeSafetyGuard(rule, lambda: "https://other.example.net")
    assert guard("mouse_click", {})
    guard = RuntimeSafetyGuard(rule, lambda: "https://example.com")
    assert guard("keyboard_type", {"text": "password=bad"})
    assert guard("keyboard_type", {"text": "search"}) is None


def test_chrome_command_and_url_observer_are_isolated(tmp_path: Path) -> None:
    """Chrome 仅配置回环调试端点，观察器仅接受 page URL。"""
    chrome = IsolatedChrome(19001, chrome_path="chrome")
    command = chrome.command("https://example.com", tmp_path)
    assert "--remote-debugging-address=127.0.0.1" in command
    observer = UrlObserver(
        19001, fetch=lambda _: b'[{"type":"page","url":"https://example.com/a"}]'
    )
    assert observer.current_url() == "https://example.com/a"


def test_trajectory_binds_click_to_move_and_validates(tmp_path: Path) -> None:
    """点击继承同一 ViewFrame 的移动坐标，最后完成动作可通过本地校验。"""
    image = tmp_path / "frame.png"
    image.write_bytes(b"png")
    recorder = EvaluationStepRecorder(
        _task(), _rule(), tmp_path / "task", lambda: "https://example.com"
    )
    recorder.record(
        {"tool_name": "mouse_move", "arguments": {"x": 12, "y": 34}, "images": [str(image)]}
    )
    recorder.record(
        {"tool_name": "mouse_click", "arguments": {}, "images": [str(image)], "reasoning": "click"}
    )
    recorder.record(
        {"tool_name": "task_complete", "arguments": {"summary": "done"}, "images": [str(image)]}
    )
    recorder.record(
        {
            "tool_name": "screenshot",
            "images": [str(image)],
            "ok": True,
            "completion_post_observation": True,
        }
    )
    target = recorder.write_and_validate()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["action_history"][1]["action"]["action_description"] == "CLICK(12,34)"


def test_invalid_trajectory_and_missing_webjudge_credential_do_not_run(tmp_path: Path) -> None:
    """损坏轨迹与缺凭据分别在调用评测器前失败。"""
    with pytest.raises(TrajectoryValidationError):
        validate_v2({"schema_version": "online-mind2web-v2"}, tmp_path)
    with pytest.raises(WebJudgeError, match="未配置"):
        run_webjudge(
            upstream_root=tmp_path,
            trajectories_dir=tmp_path,
            output_path=tmp_path / "judge.jsonl",
            judge_model="test",
            api_key_env="MISSING_TEST_KEY",
        )


def test_webjudge_parses_task_labels_without_exposing_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """模拟 Judge 原始输出可回填 task 标签，凭据仅由子进程环境接收。"""
    root, trajectories = tmp_path / "upstream", tmp_path / "trajectories"
    (root / "src").mkdir(parents=True)
    (root / "src" / "run.py").write_text("", encoding="utf-8")
    result_dir = trajectories / "sample"
    recorder = EvaluationStepRecorder(_task(), _rule(), result_dir, lambda: "https://example.com")
    image = tmp_path / "frame.png"
    image.write_bytes(b"png")
    recorder.record(
        {"tool_name": "mouse_move", "arguments": {"x": 1, "y": 2}, "images": [str(image)]}
    )
    recorder.record(
        {"tool_name": "task_complete", "arguments": {"summary": "done"}, "images": [str(image)]}
    )
    recorder.record(
        {
            "tool_name": "screenshot",
            "images": [str(image)],
            "ok": True,
            "completion_post_observation": True,
        }
    )
    recorder.write_and_validate()
    monkeypatch.setenv("TEST_JUDGE_KEY", "secret")

    def runner(command: list[str], **kwargs: object) -> object:
        assert "secret" not in command
        output = Path(command[command.index("--output_path") + 1])
        output.mkdir(exist_ok=True)
        (
            output / "WebJudge_Online_Mind2Web_eval_test_score_threshold_3_auto_eval_results.json"
        ).write_text('{"task_id":"sample","predicted_label":1}\n', encoding="utf-8")
        return type("Completed", (), {"returncode": 0})()

    assert run_webjudge(
        upstream_root=root,
        trajectories_dir=trajectories,
        output_path=tmp_path / "judge",
        judge_model="test",
        api_key_env="TEST_JUDGE_KEY",
        runner=runner,
    ) == {"sample": 1}


def test_summary_keeps_environment_out_of_model_denominator() -> None:
    """环境失败不进入模型成功率，未知 Token 不按零累计。"""
    summary = EvaluationSummary(
        2,
        [
            TaskMetrics(
                "a",
                PreflightStatus.READY,
                executed=True,
                webjudge_label=1,
                reference_length=2,
                action_steps=2,
            ),
            TaskMetrics("b", PreflightStatus.SITE_UNREACHABLE, reference_length=2),
        ],
    ).to_dict()
    assert summary["model_task_success_rate"] == 1
    assert summary["environment_unexecutable_tasks"] == 1
    assert summary["total_tokens"] is None
    assert summary["end_to_end_success_rate"] == 0.5


def test_guard_observations_do_not_consume_action_budget() -> None:
    """截图和 hover 不计入受限网页交互动作预算。"""
    guard = RuntimeSafetyGuard(
        SafetyRule("sample", ("example.com",), 1, 20), lambda: "https://example.com"
    )
    assert guard("screenshot", {}) is None
    assert guard("mouse_move", {"x": 1, "y": 1}) is None
    assert guard("mouse_click", {}) is None
    assert guard("mouse_click", {})
