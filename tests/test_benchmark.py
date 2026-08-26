"""本地 Web 评测场的离线合同测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from max_gui.benchmark.evaluator import score_state
from max_gui.benchmark.runner import validate_comparison
from max_gui.benchmark.tasks import load_task_suite
from max_gui.benchmark.web import create_benchmark_app


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
