"""本地运行可观测性：事件信封、JSONL 增量记录、恢复与故障降级。"""

from __future__ import annotations

import json
from pathlib import Path

from max_gui.observability import RunEvent, RunRecorder, safe_error_summary


def _read_events(path: Path) -> list[dict]:
    """读取测试产生的全部合法 JSONL 事件。"""
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            events.append(raw)
    return events


def test_event_envelope_sequence_and_incremental_flush(tmp_path: Path) -> None:
    """事件信封齐全、顺序递增，record 返回后文件立即可读。"""
    recorder = RunRecorder(tmp_path / "runs", "session-1", run_id="run-fixed")
    first = recorder.record("run.started")
    second = recorder.record(
        "tool.started",
        iteration=2,
        subtask="截图",
        data={"call_id": "call-1", "tool_name": "screenshot"},
    )
    events = _read_events(recorder.path)
    assert first.schema_version == 1
    assert first.sequence == 1
    assert second.sequence == 2
    assert second.event_id == "run-fixed:2"
    assert second.timestamp.endswith(("+08:00", "+00:00")) or second.timestamp[-6:-5] in {"+", "-"}
    assert events[-1]["subtask"] == "截图"
    assert events[-1]["iteration"] == 2
    assert recorder.unfinished_tools == {"call-1": "screenshot"}
    recorder.close()


def test_resume_skips_broken_tail_and_preserves_existing_file(tmp_path: Path) -> None:
    """残缺末行被保留为坏行，恢复从最后合法顺序继续追加。"""
    runs = tmp_path / "runs"
    first = RunRecorder(runs, "session-1", run_id="run-fixed")
    first.record("run.started")
    first.record(
        "tool.started",
        data={"call_id": "call-1", "tool_name": "mouse_click"},
    )
    first.close()
    with first.path.open("a", encoding="utf-8") as handle:
        handle.write('{"sequence":')

    resumed_events: list[RunEvent] = []
    resumed = RunRecorder(
        runs,
        "session-1",
        run_id="run-fixed",
        on_event=resumed_events.append,
    )
    assert resumed.unfinished_tools == {"call-1": "mouse_click"}
    event = resumed.record("run.resumed")
    resumed.close()
    assert event.sequence == 3
    assert resumed_events[-1].event_type == "run.resumed"
    assert [item["sequence"] for item in _read_events(first.path)] == [1, 2, 3]
    assert '{"sequence":' in first.path.read_text(encoding="utf-8")


def test_summary_tracks_calls_and_terminal_data(tmp_path: Path) -> None:
    """汇总分别统计模型、工具、失败、耗时与最高轮次。"""
    recorder = RunRecorder(tmp_path / "runs", "session-1")
    recorder.record("model.started", iteration=1)
    recorder.record("model.completed", iteration=1, data={"duration_ms": 40})
    recorder.record(
        "tool.started",
        iteration=2,
        data={"call_id": "a", "tool_name": "screenshot"},
    )
    recorder.record("tool.failed", iteration=2, data={"call_id": "a", "duration_ms": 5})
    summary = recorder.summary(final_status="error")
    assert summary["model_calls"] == 1
    assert summary["model_duration_ms"] == 40
    assert summary["tool_calls"] == 1
    assert summary["tool_failures"] == 1
    assert summary["tool_successes"] == 0
    assert summary["iterations"] == 2
    assert summary["final_status"] == "error"
    assert "prompt_tokens" not in summary
    assert "completion_tokens" not in summary
    assert "total_tokens" not in summary
    recorder.close()


def test_summary_accumulates_known_usage_and_skips_unknown(tmp_path: Path) -> None:
    """两次已知用量相加；未知调用不把累计写成 0。"""
    recorder = RunRecorder(tmp_path / "runs", "session-1")
    recorder.record(
        "model.completed",
        data={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    recorder.record("model.completed", data={"duration_ms": 1})
    recorder.record(
        "model.completed",
        data={"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27},
    )
    summary = recorder.summary(final_status="done")
    assert summary["prompt_tokens"] == 30
    assert summary["completion_tokens"] == 12
    assert summary["total_tokens"] == 42
    recorder.close()

    unknown = RunRecorder(tmp_path / "runs", "session-2", run_id="run-unknown")
    unknown.record("model.completed", data={"duration_ms": 9})
    empty = unknown.summary(final_status="done")
    assert "prompt_tokens" not in empty
    unknown.close()


def test_resume_continues_token_usage_totals(tmp_path: Path) -> None:
    """恢复既有 JSONL 后继续累加后续已知用量。"""
    runs = tmp_path / "runs"
    first = RunRecorder(runs, "session-1", run_id="run-fixed")
    first.record(
        "model.completed",
        data={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    )
    first.close()
    resumed = RunRecorder(runs, "session-1", run_id="run-fixed")
    resumed.record(
        "model.completed",
        data={"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27},
    )
    summary = resumed.summary()
    assert summary["prompt_tokens"] == 30
    assert summary["completion_tokens"] == 12
    assert summary["total_tokens"] == 42
    resumed.close()


def test_unlimited_retention_does_not_touch_other_runs(tmp_path: Path) -> None:
    """新记录器不会清理、轮转或覆盖目录里的旧运行文件。"""
    runs = tmp_path / "runs"
    runs.mkdir()
    old = runs / "run-old.jsonl"
    old.write_text("旧日志\n", encoding="utf-8")
    recorder = RunRecorder(runs, "session-1", run_id="run-new")
    recorder.record("run.started")
    recorder.close()
    assert old.read_text(encoding="utf-8") == "旧日志\n"
    assert (runs / "run-new.jsonl").is_file()


def test_write_failure_is_reported_in_memory_and_does_not_raise(tmp_path: Path) -> None:
    """运行目录被普通文件占用时，磁盘禁用且回调得到中文诊断。"""
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    received: list[RunEvent] = []
    recorder = RunRecorder(blocked, "session-1", on_event=received.append)
    original = recorder.record("run.started")
    later = recorder.record("run.completed", data={"final_status": "done"})
    assert original.event_type == "run.started"
    assert later.event_type == "run.completed"
    assert recorder.disk_enabled is False
    failures = [event for event in received if event.event_type == "recorder.failed"]
    assert len(failures) == 1
    assert failures[0].data["message"] == "运行日志写入失败"


def test_safe_error_summary_redacts_common_secrets() -> None:
    """异常摘要遮蔽 Bearer、api_key 与 token 值。"""
    raw = "Authorization: Bearer abc123 api_key=secret token: hidden"
    summary = safe_error_summary(ValueError(raw))
    assert "abc123" not in summary
    assert "secret" not in summary
    assert "hidden" not in summary
    assert summary.count("***") == 3
