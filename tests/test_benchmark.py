"""Vue 评测场、v2 任务集和报告边界的离线合同测试。"""

from __future__ import annotations

import json
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


def test_v2_suite_contains_one_hundred_explicit_layered_tasks() -> None:
    """v2 任务集含 100 条唯一任务，覆盖难度、能力和固定冒烟集。"""
    suite = load_task_suite()
    assert suite.version == "web-gui-v2"
    assert len(suite.tasks) == len({task.id for task in suite.tasks}) == 100
    assert {task.difficulty for task in suite.tasks} == {"easy", "medium", "hard"}
    assert len(select_task_batch(suite, 10)) == 10
    assert {task.difficulty for task in select_task_batch(suite, 10)} == {"easy", "medium", "hard"}
    assert select_task_batch(suite, 100) == suite.tasks
    assert {task.route for task in suite.tasks} == {"/arena/home"}
    assert all("本题对象为" not in task.instruction for task in suite.tasks)
    assert all(1 <= task.expected_steps <= 3 for task in suite.tasks if task.difficulty == "easy")
    assert all(5 <= task.expected_steps <= 6 for task in suite.tasks if task.difficulty == "medium")
    assert all(task.expected_steps >= 7 for task in suite.tasks if task.difficulty == "hard")
    assert all(
        sum(checkpoint.startswith("visited_") for checkpoint in task.required_checkpoints) >= 2
        for task in suite.tasks
        if task.difficulty == "hard"
    )


def test_v2_loader_rejects_copy_expansion_fields(tmp_path: Path) -> None:
    """复制展开字段即使任务数正确也必须被加载器拒绝。"""
    raw = json.loads(
        (Path(__file__).parents[1] / "artifacts/benchmarks/web-gui-v2.json").read_text()
    )
    raw["copies_per_template"] = 1
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="复制"):
        load_task_suite(path)


def test_vue_home_business_api_and_hidden_control_state() -> None:
    """Vue 入口、可见业务 API 与不在页面显示的控制面保持隔离。"""
    suite = load_task_suite()
    client = TestClient(create_benchmark_app(suite))
    home = client.get("/")
    assert home.status_code == 200
    assert "/api/state" not in home.text
    listing = client.get("/api/arena/items?query=评测&page=1")
    assert listing.status_code == 200
    assert "success" not in listing.text and "instruction" not in listing.text
    task = suite.tasks[0]
    assert client.post("/api/reset", json={"task_id": task.id}).json()["route"] == task.route
    assert client.get("/api/state").status_code == 200


def test_every_business_route_renders_and_unknown_route_is_rejected() -> None:
    """完整网站的九个业务路由均回退 Vue 入口，未知路由不被掩盖。"""
    suite = load_task_suite()
    client = TestClient(create_benchmark_app(suite))
    for route in {
        "/arena/home",
        "/arena/inbox",
        "/arena/projects",
        "/arena/tasks",
        "/arena/calendar",
        "/arena/automation",
        "/arena/team",
        "/arena/reports",
        "/arena/settings",
    }:
        assert client.get(route).status_code == 200
    assert client.get("/arena/unknown").status_code == 404


def test_navigation_checkpoint_requires_visible_navigation_event() -> None:
    """地址栏直达不产生检查点，只有页面点击调用的导航业务事件会被评分。"""
    suite = load_task_suite()
    client = TestClient(create_benchmark_app(suite))
    client.post("/api/reset", json={"task_id": suite.tasks[0].id})
    assert client.get("/arena/projects").status_code == 200
    assert "visited_projects" not in client.get("/api/state").json()
    assert client.post("/api/arena/navigation", json={"section": "projects"}).json() == {
        "route": "/arena/projects"
    }
    state = client.get("/api/state").json()
    assert state["visited_projects"] is True
    assert state["visited_pages"] == ["projects"]


def test_cross_page_business_state_supports_functional_scoring() -> None:
    """跨页创建流程按导航检查点和最终实体字段评分，而不是按最后动作代号评分。"""
    suite = load_task_suite()
    task = next(item for item in suite.tasks if item.id == "arena-082")
    client = TestClient(create_benchmark_app(suite))
    client.post("/api/reset", json={"task_id": task.id})
    client.post("/api/arena/navigation", json={"section": "projects"})
    client.post("/api/arena/navigation", json={"section": "tasks"})
    client.post(
        "/api/arena/items",
        json={
            "name": "建立曙光风险台账",
            "owner": "王晨",
            "priority": "normal",
            "status": "进行中",
        },
    )
    assert score_state(client.get("/api/state").json(), task.success).strict_success is True


def test_business_actions_validate_edit_batch_and_reset() -> None:
    """业务 API 支持校验、编辑、批量操作，并在重置后抹除题间改动。"""
    suite = load_task_suite()
    client = TestClient(create_benchmark_app(suite))
    client.post("/api/reset", json={"task_id": suite.tasks[0].id})
    assert client.post("/api/arena/items", json={"name": "", "owner": "张三"}).status_code == 422
    created = client.post("/api/arena/items", json={"name": "核验", "owner": "张三"}).json()
    changed = client.put(f"/api/arena/items/{created['id']}", json={"name": "已编辑"}).json()
    assert changed["name"] == "已编辑"
    assert client.post(
        "/api/arena/batch", json={"ids": [created["id"]], "action": "complete"}
    ).json() == {"updated": 1}
    client.post("/api/reset", json={"task_id": suite.tasks[0].id})
    assert all(item["name"] != "已编辑" for item in client.get("/api/arena/items").json()["items"])


def test_home_starts_selected_batch_and_rejects_invalid_or_duplicate_requests() -> None:
    """首页仅允许 10/100 两种 JSON 启动请求，重复请求由控制器拒绝。"""
    started: list[int] = []

    def start(task_count: int) -> bool:
        """记录第一次启动并模拟运行互斥。"""
        if started:
            return False
        started.append(task_count)
        return True

    client = TestClient(create_benchmark_app(load_task_suite(), start=start))
    assert client.post("/api/start", json={"task_count": 20}).status_code == 422
    assert client.post("/api/start", json={"task_count": 10}).json() == {
        "started": True,
        "task_count": 10,
    }
    assert client.post("/api/start", json={"task_count": 100}).status_code == 409


def test_interrupt_endpoint_only_accepts_running_batch() -> None:
    """中断接口只转发运行中批次的请求，并向页面返回明确状态。"""
    interrupted = False

    def interrupt() -> bool:
        """模拟运行中的控制器仅接受第一次中断请求。"""
        nonlocal interrupted
        if interrupted:
            return False
        interrupted = True
        return True

    client = TestClient(create_benchmark_app(load_task_suite(), interrupt=interrupt))
    assert client.post("/api/interrupt").json() == {"interrupted": True}
    assert client.post("/api/interrupt").status_code == 409


def test_controller_uses_selected_batch_and_rejects_switching_while_running(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """控制器只以首页首次选择的 v2 批次更新进度。"""
    monkeypatch.setattr("max_gui.benchmark.service.threading.Thread.start", lambda _thread: None)
    suite = load_task_suite()
    controller = BenchmarkController(
        settings, suite, BenchmarkStore(suite), "http://127.0.0.1:8765"
    )
    assert controller.start(10) is True
    assert controller.progress()["total"] == 10
    assert controller.start(100) is False


def test_controller_interrupts_running_batch_without_allowing_restart(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """中断请求会切换进度状态，并在后台尚未退出时拒绝再次启动。"""
    monkeypatch.setattr("max_gui.benchmark.service.threading.Thread.start", lambda _thread: None)
    suite = load_task_suite()
    controller = BenchmarkController(
        settings, suite, BenchmarkStore(suite), "http://127.0.0.1:8765"
    )
    assert controller.start(10) is True
    assert controller.interrupt() is True
    assert controller.progress()["status"] == "interrupting"
    assert controller.start(100) is False
    assert controller.interrupt() is False


def test_report_records_requested_task_count_and_unknown_tokens(tmp_path: Path) -> None:
    """报告保留请求范围，且未知 Token 仍使用 None/JSON null 语义。"""
    result = TaskResult(
        "arena-001", "web-gui-v2", "test", True, 1, 1, "completed", 100, 2, 0, 0, (), None
    )
    summary = write_report([result], tmp_path / "report.json", requested_tasks=10)
    assert summary["requested_tasks"] == 10 and summary["known_token_samples"] == 0


def test_score_and_comparison_contracts_remain_independent() -> None:
    """评分只比较业务状态，对比运行仍要求实验条件一致。"""
    assert score_state({"saved": True}, {"saved": True}).strict_success is True
    common = {
        "suite_version": "web-gui-v2",
        "temperature": 0,
        "max_iterations": 20,
        "timeout_seconds": 90,
        "browser": "Chrome",
    }
    validate_comparison(common, {**common, "model": "lora"})
