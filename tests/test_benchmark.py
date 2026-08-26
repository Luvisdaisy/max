"""本地 Web 评测场的离线合同测试。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from max_gui.benchmark.evaluator import score_state
from max_gui.benchmark.report import TaskResult, write_report
from max_gui.benchmark.runner import validate_comparison
from max_gui.benchmark.service import BenchmarkController
from max_gui.benchmark.tasks import load_task_suite, select_task_batch
from max_gui.benchmark.web import BenchmarkStore, create_benchmark_app
from max_gui.config import Settings


def test_suite_expands_to_one_hundred_tasks() -> None:
    """v1 任务集展开后覆盖 100 条任务和四种类别。"""
    suite = load_task_suite()
    assert len(suite.tasks) == 100
    assert {task.category for task in suite.tasks} == {
        "basic",
        "single_page",
        "multi_step",
        "robustness",
    }


def test_select_ten_tasks_has_stable_difficulty_coverage() -> None:
    """10 条冒烟批次固定包含 4 easy、3 medium、3 hard，且保留原任务顺序。"""
    suite = load_task_suite()
    selected = select_task_batch(suite, 10)
    positions = [suite.tasks.index(task) for task in selected]
    assert len(selected) == 10
    assert Counter(task.difficulty for task in selected) == {"easy": 4, "medium": 3, "hard": 3}
    assert positions == sorted(positions)
    assert select_task_batch(suite, 100) == suite.tasks
    with pytest.raises(ValueError, match="10 或 100"):
        select_task_batch(suite, 20)


def test_home_starts_selected_batch_and_rejects_invalid_or_duplicate_requests() -> None:
    """首页仅提交 10/100；非法值与运行中的第二次启动分别被拒绝。"""
    started: list[int] = []

    def start(task_count: int) -> bool:
        """记录首次请求，并模拟控制器对重复启动返回假。"""
        if started:
            return False
        started.append(task_count)
        return True

    suite = load_task_suite()
    client = TestClient(create_benchmark_app(suite, start=start))
    home = client.get("/").text
    assert "运行 10 条" in home and "运行 100 条" in home
    assert client.post("/api/start", data={"task_count": "20"}).status_code == 422
    response = client.post("/api/start", data={"task_count": "10"})
    assert response.json() == {"started": True, "task_count": 10}
    assert started == [10]
    assert client.post("/api/start", data={"task_count": "100"}).status_code == 409


def test_controller_uses_selected_batch_and_rejects_switching_while_running(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """控制器只以首页首次选择的批次更新进度，运行中不能改为另一规模。"""
    monkeypatch.setattr("max_gui.benchmark.service.threading.Thread.start", lambda _thread: None)
    suite = load_task_suite()
    controller = BenchmarkController(
        settings,
        suite,
        BenchmarkStore(suite),
        "http://127.0.0.1:8765",
    )
    assert controller.progress()["total"] == 0
    assert controller.start(10) is True
    assert controller.progress()["total"] == 10
    assert controller.start(100) is False


def test_report_records_requested_task_count(tmp_path: Path) -> None:
    """10 条报告保留请求规模，避免被误读为完整 100 条评测。"""
    result = TaskResult(
        task_id="form-basic-01-v1",
        suite_version="web-gui-v1",
        model="test-model",
        strict_success=True,
        criteria_passed=2,
        criteria_total=2,
        termination_reason="completed",
        duration_ms=100,
        tool_calls=2,
        tool_failures=0,
        invalid_actions=0,
        violations=(),
        total_tokens=None,
    )
    summary = write_report([result], tmp_path / "web-gui-eval-10.json", requested_tasks=10)
    assert summary["requested_tasks"] == 10


def test_form_reset_save_and_score() -> None:
    """重置后经普通表单保存，状态可由评分器独立判定。"""
    suite = load_task_suite()
    task = next(item for item in suite.tasks if item.id == "form-multi-01-v1")
    client = TestClient(create_benchmark_app(suite))
    assert client.post("/api/reset", json={"task_id": task.id}).json()["route"] == "/form"
    response = client.post("/form/save", data={"name": "周报", "priority": "high"})
    assert response.status_code == 200
    score = score_state(client.get("/api/state").json(), task.success)
    assert score.strict_success is True


def test_partial_score_and_reset_discards_previous_state() -> None:
    """部分断言不算严格成功，下一次重置不保留上次保存值。"""
    suite = load_task_suite()
    task = next(item for item in suite.tasks if item.id == "form-multi-01-v1")
    client = TestClient(create_benchmark_app(suite))
    client.post("/api/reset", json={"task_id": task.id})
    client.post("/form/save", data={"name": "周报", "priority": "normal"})
    partial = score_state(client.get("/api/state").json(), task.success)
    assert partial.strict_success is False
    assert partial.criteria_passed == 2
    client.post("/api/reset", json={"task_id": task.id})
    assert client.get("/api/state").json()["project_name"] == ""


def test_comparison_requires_same_evaluation_conditions() -> None:
    """基础模型与 LoRA 只能在一致的任务和运行限制下对比。"""
    common = {
        "suite_version": "web-gui-v1",
        "temperature": 0,
        "max_iterations": 20,
        "timeout_seconds": 90,
        "browser": "Chrome",
    }
    validate_comparison(common, {**common, "model": "lora"})
    with pytest.raises(ValueError, match="temperature"):
        validate_comparison(common, {**common, "temperature": 0.2})
