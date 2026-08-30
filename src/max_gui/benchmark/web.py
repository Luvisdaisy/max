"""Vue 评测场的回环 API、状态存储与静态产物托管。

业务 API 仅返回可见工作台数据；重置与评分状态接口仅供本地评测运行器调用。
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from max_gui.benchmark.tasks import BenchmarkTask, TaskSuite

FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "benchmark-arena" / "dist"
ARENA_SECTIONS = {
    "home",
    "inbox",
    "projects",
    "tasks",
    "calendar",
    "automation",
    "team",
    "reports",
    "settings",
}
ARENA_ROUTES = {f"/arena/{section}" for section in ARENA_SECTIONS}


class BenchmarkStore:
    """按任务保存唯一可判分的后端业务状态。"""

    def __init__(self, suite: TaskSuite) -> None:
        """登记任务并初始化工作台数据。"""
        self.tasks = {task.id: task for task in suite.tasks}
        self.current_id: str | None = None
        self.state: dict[str, Any] = {}
        self.items: list[dict[str, Any]] = []
        self.projects: list[dict[str, Any]] = []
        self.members: list[dict[str, Any]] = []
        self.activity: list[dict[str, str]] = []
        self.undo: dict[str, Any] | None = None
        self._restore_baseline()

    def _restore_baseline(self) -> None:
        """恢复完整协作工作台基线，避免任务间共享实体或活动记录。"""
        self.items = _seed_items()
        self.projects = _seed_projects()
        self.members = _seed_members()
        self.activity = _seed_activity()
        self.undo = None

    def reset(self, task_id: str) -> BenchmarkTask:
        """将当前任务和业务数据恢复为隔离初始状态。"""
        task = self.tasks[task_id]
        self.current_id = task.id
        self._restore_baseline()
        self.state = {
            "last_action": "",
            "selected_ids": [],
            "visited_pages": [],
            **deepcopy(task.initial_state),
        }
        return task

    def record_activity(self, kind: str, detail: str) -> None:
        """记录可见业务活动，并限制时间线长度以保持页面稳定。"""
        self.activity.insert(0, {"time": _timestamp(), "kind": kind, "detail": detail})
        del self.activity[12:]

    def current(self) -> BenchmarkTask:
        """返回当前任务；未重置时拒绝读取评分状态。"""
        if self.current_id is None:
            raise RuntimeError("尚未重置任务")
        return self.tasks[self.current_id]

    def visible_items(
        self, query: str, priority: str, sort: str, page: int, assignee: str = "all"
    ) -> dict[str, Any]:
        """按可见筛选、排序和分页规则返回工作台数据。"""
        if query:
            self.state["current_query"] = query
        if priority != "all":
            self.state["current_priority"] = priority
        if sort != "updated_desc":
            self.state["current_sort"] = sort
        if page > 1:
            self.state["current_page"] = page
        if assignee != "all":
            self.state["current_assignee"] = assignee
        items = [
            item
            for item in self.items
            if query.lower() in f"{item['name']} {item['owner']}".lower()
        ]
        if priority != "all":
            items = [item for item in items if item["priority"] == priority]
        if assignee != "all":
            items = [item for item in items if item["owner"] == assignee]
        if sort == "name":
            items.sort(key=lambda item: str(item["name"]))
        else:
            items.sort(key=lambda item: str(item["updated_at"]), reverse=True)
        page_size = 6
        start = max(page - 1, 0) * page_size
        if (query or priority != "all" or assignee != "all") and not items:
            self.state["empty_filter"] = True
        return {
            "items": items[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": len(items),
            "has_filters": bool(query or priority != "all" or assignee != "all"),
        }


def create_benchmark_app(
    suite: TaskSuite,
    *,
    start: Callable[[int], bool] | None = None,
    progress: Callable[[], dict[str, Any]] | None = None,
    interrupt: Callable[[], bool] | None = None,
    dist_dir: Path = FRONTEND_DIST,
) -> FastAPI:
    """创建单进程 Vue 静态站点、业务 API 和受限评测控制面。"""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    store = BenchmarkStore(suite)
    app.state.benchmark_store = store

    @app.get("/api/progress")
    async def get_progress() -> dict[str, Any]:
        """返回首页轮询所需且不含任务答案的进度。"""
        return progress() if progress else {"status": "ready", "completed": 0, "total": 0}

    @app.post("/api/start")
    async def start_run(payload: dict[str, Any]) -> dict[str, Any]:
        """从 Vue 首页显式启动 10 或 100 条评测。"""
        task_count = payload.get("task_count")
        if start is None:
            raise HTTPException(status_code=409, detail="当前服务未配置自动评测器")
        if task_count not in {10, 100}:
            raise HTTPException(status_code=422, detail="任务数量仅支持 10 或 100")
        try:
            started = start(task_count)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not started:
            raise HTTPException(status_code=409, detail="评测正在运行")
        return {"started": True, "task_count": task_count}

    @app.post("/api/interrupt")
    async def interrupt_run() -> dict[str, bool]:
        """请求中断当前评测批次；空闲时明确拒绝该请求。"""
        if interrupt is None or not interrupt():
            raise HTTPException(status_code=409, detail="当前没有可中断的评测")
        return {"interrupted": True}

    @app.post("/api/reset")
    async def reset(payload: dict[str, str]) -> dict[str, Any]:
        """仅供运行器按任务标识复位并取得业务路由。"""
        try:
            task = store.reset(payload["task_id"])
        except (KeyError, TypeError) as exc:
            raise HTTPException(status_code=404, detail="未知任务") from exc
        return {"task_id": task.id, "route": task.route}

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        """仅返回评分器读取的最小后端状态。"""
        try:
            store.current()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return dict(store.state)

    @app.get("/api/arena/items")
    async def list_items(
        query: str = "",
        priority: str = "all",
        sort: str = "updated_desc",
        page: int = 1,
        assignee: str = "all",
    ) -> dict[str, Any]:
        """返回 Vue 工作台可见的筛选、排序和分页任务列表。"""
        if (
            priority not in {"all", "high", "normal", "low"}
            or sort not in {"updated_desc", "name"}
            or assignee not in {"all", *(member["name"] for member in store.members)}
        ):
            raise HTTPException(status_code=422, detail="筛选条件无效")
        return store.visible_items(query, priority, sort, page, assignee)

    @app.get("/api/arena/summary")
    async def arena_summary() -> dict[str, Any]:
        """返回工作台、报表和团队页面共用的可见聚合数据。"""
        counts = {
            status: sum(item["status"] == status for item in store.items)
            for status in ("待处理", "进行中", "已完成", "已逾期")
        }
        workload = {
            member["name"]: sum(item["owner"] == member["name"] for item in store.items)
            for member in store.members
        }
        total_items = len(store.items)
        completed_items = counts["已完成"]
        overdue_project = max(
            projects := [
                {
                    **project,
                    "task_count": sum(item["project"] == project["name"] for item in store.items),
                    "overdue": sum(
                        item["project"] == project["name"] and item["status"] == "已逾期"
                        for item in store.items
                    ),
                }
                for project in store.projects
            ],
            key=lambda project: project["overdue"],
        )
        return {
            "counts": counts,
            "projects": projects,
            "members": [
                {**member, "workload": f"{workload[member['name']]} 项任务"}
                for member in store.members
            ],
            "automations": _seed_automations(store.state),
            "events": _seed_events(),
            "activity": store.activity,
            "metrics": [
                {
                    "label": "完成率",
                    "value": f"{round(completed_items / total_items * 100) if total_items else 0}%",
                    "detail": f"当前已完成 {completed_items} / {total_items} 项任务",
                },
                {
                    "label": "逾期任务最多",
                    "value": overdue_project["name"],
                    "detail": f"当前共有 {overdue_project['overdue']} 条逾期任务",
                },
                {
                    "label": "活跃协作成员",
                    "value": str(sum(value > 0 for value in workload.values())),
                    "detail": "当前至少负责一项任务的成员数",
                },
            ],
            "settings": {
                "theme": str(store.state.get("theme", "浅色")),
                "compact": bool(store.state.get("compact", False)),
            },
        }

    @app.post("/api/arena/navigation")
    async def record_navigation(payload: dict[str, Any]) -> dict[str, str]:
        """记录由可见站内导航触发的页面访问，地址栏直达不会调用该接口。"""
        section = str(payload.get("section") or "")
        if section not in ARENA_SECTIONS:
            raise HTTPException(status_code=422, detail="未知导航目标")
        pages = store.state.setdefault("visited_pages", [])
        if section not in pages:
            pages.append(section)
        store.state[f"visited_{section}"] = True
        store.state["last_action"] = "navigate"
        return {"route": f"/arena/{section}"}

    @app.post("/api/arena/view/{item_id}")
    async def view_item(item_id: str) -> dict[str, Any]:
        """记录用户从列表打开的任务详情并返回该业务实体。"""
        item = _find_item(store, item_id)
        store.state["viewed_item"] = item["name"]
        store.state["last_action"] = "view"
        return item

    @app.get("/api/arena/projects/{project_name}")
    async def project_detail(project_name: str) -> dict[str, Any]:
        """返回项目风险、里程碑和关联任务，供可见详情页读取。"""
        project = next((item for item in store.projects if item["name"] == project_name), None)
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        related = [item for item in store.items if item["project"] == project_name]
        risk = max(
            related, key=lambda item: (item["status"] == "已逾期", item["priority"] == "high")
        )
        store.state[f"observed_project_{project_name}"] = True
        store.state["observed_risk_task"] = risk["name"]
        store.state["observed_member_workload"] = {
            member["name"]: sum(item["owner"] == member["name"] for item in store.items)
            for member in store.members
        }
        store.state["last_action"] = "project_detail"
        return {
            **project,
            "tasks": related,
            "risk_task": risk["name"],
            "milestones": project["milestones"],
            "members": [
                {
                    **member,
                    "workload": sum(item["owner"] == member["name"] for item in store.items),
                }
                for member in store.members
            ],
        }

    @app.post("/api/arena/projects/{project_name}/tasks/{item_id}")
    async def open_project_task(project_name: str, item_id: str) -> dict[str, Any]:
        """从项目详情打开关联任务，并记录不可由地址栏伪造的来源检查点。"""
        item = _find_item(store, item_id)
        if item["project"] != project_name:
            raise HTTPException(status_code=422, detail="任务不属于该项目")
        if not store.state.get(f"observed_project_{project_name}"):
            raise HTTPException(status_code=409, detail="请先通过项目详情读取关联任务")
        store.state["project_task_source"] = project_name
        store.state["viewed_item"] = item["name"]
        store.state["visited_tasks"] = True
        store.state.setdefault("visited_pages", []).append("tasks")
        store.state["last_action"] = "project_task"
        return item

    @app.post("/api/arena/settings")
    async def update_settings(payload: dict[str, Any]) -> dict[str, Any]:
        """更新主题或紧凑布局，并把最终设置写入评分状态。"""
        if "theme" in payload:
            theme = str(payload["theme"])
            if theme not in {"浅色", "深色"}:
                raise HTTPException(status_code=422, detail="主题无效")
            store.state["theme"] = theme
        if "compact" in payload:
            store.state["compact"] = bool(payload["compact"])
        store.state["last_action"] = "settings"
        return {
            "theme": store.state.get("theme", "浅色"),
            "compact": store.state.get("compact", False),
        }

    @app.post("/api/arena/automations/{automation_id}")
    async def toggle_automation(automation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """切换固定自动化规则，并记录可由任务断言的最终开关状态。"""
        if automation_id not in {"overdue-reminder", "high-priority-notice", "daily-summary"}:
            raise HTTPException(status_code=404, detail="自动化规则不存在")
        enabled = bool(payload.get("enabled"))
        store.state[f"automation_{automation_id}"] = enabled
        store.state["last_action"] = "automation"
        return {"id": automation_id, "enabled": enabled}

    @app.post("/api/arena/items")
    async def create_item(payload: dict[str, Any]) -> JSONResponse:
        """创建一条可见工作台任务，并显示必填校验错误。"""
        name = str(payload.get("name") or "").strip()
        owner = str(payload.get("owner") or "").strip()
        if not name or not owner:
            store.state["validation_error"] = True
            raise HTTPException(status_code=422, detail="任务名称和负责人不能为空")
        priority = str(payload.get("priority") or "normal")
        status = str(payload.get("status") or "待处理")
        if priority not in {"high", "normal", "low"} or status not in _ITEM_STATUSES:
            raise HTTPException(status_code=422, detail="优先级或状态无效")
        if owner not in {member["name"] for member in store.members}:
            raise HTTPException(status_code=422, detail="负责人不存在")
        item = _item(
            str(len(store.items) + 1),
            name,
            owner,
            priority,
            status,
            str(payload.get("description") or ""),
        )
        item["due_date"] = str(payload.get("due_date") or item["due_date"]).strip()
        item["comment_draft"] = str(payload.get("comment_draft") or "").strip()
        if isinstance(payload.get("tags"), list):
            item["tags"] = [str(tag).strip() for tag in payload["tags"] if str(tag).strip()]
        if isinstance(payload.get("subtasks"), list):
            item["subtasks"] = [
                str(subtask).strip() for subtask in payload["subtasks"] if str(subtask).strip()
            ]
        if item["due_date"] and not _is_iso_date(item["due_date"]):
            raise HTTPException(status_code=422, detail="截止日期必须为 YYYY-MM-DD")
        store.items.insert(0, item)
        store.state["created_name"] = item["name"]
        store.state["created_owner"] = item["owner"]
        store.state["created_priority"] = item["priority"]
        store.state["created_status"] = item["status"]
        store.state["created_due_date"] = item["due_date"]
        store.state["created_tags"] = list(item["tags"])
        store.state["created_subtasks"] = list(item["subtasks"])
        _record_action(store, "create")
        store.record_activity("创建任务", f"新建「{item['name']}」并分配给{item['owner']}")
        return JSONResponse(item, status_code=201)

    @app.put("/api/arena/items/{item_id}")
    async def update_item(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """更新可见任务字段，找不到目标时返回 404。"""
        item = _find_item(store, item_id)
        expected_version = payload.get("expected_version")
        if expected_version is not None and not _matches_version(expected_version, item["version"]):
            store.state["version_conflict"] = True
            raise HTTPException(status_code=409, detail="任务已被其他协作成员更新，请刷新后重试")
        for key in (
            "name",
            "owner",
            "priority",
            "status",
            "description",
            "due_date",
            "comment_draft",
        ):
            if key in payload:
                item[key] = str(payload[key]).strip()
        if "tags" in payload and isinstance(payload["tags"], list):
            item["tags"] = [str(tag).strip() for tag in payload["tags"] if str(tag).strip()]
        if "subtasks" in payload and isinstance(payload["subtasks"], list):
            item["subtasks"] = [
                str(task).strip() for task in payload["subtasks"] if str(task).strip()
            ]
        if not item["name"] or not item["owner"]:
            raise HTTPException(status_code=422, detail="任务名称和负责人不能为空")
        if item["owner"] not in {member["name"] for member in store.members}:
            raise HTTPException(status_code=422, detail="负责人不存在")
        if (
            item["priority"] not in {"high", "normal", "low"}
            or item["status"] not in _ITEM_STATUSES
        ):
            raise HTTPException(status_code=422, detail="优先级或状态无效")
        if item["due_date"] and not _is_iso_date(item["due_date"]):
            raise HTTPException(status_code=422, detail="截止日期必须为 YYYY-MM-DD")
        item["updated_at"] = _timestamp()
        item["version"] = int(item["version"]) + 1
        store.state["updated_item"] = item["name"]
        store.state["updated_owner"] = item["owner"]
        store.state["updated_priority"] = item["priority"]
        store.state["updated_status"] = item["status"]
        store.state["updated_due_date"] = item["due_date"]
        store.state["updated_tags"] = list(item["tags"])
        store.state["updated_subtasks"] = list(item["subtasks"])
        store.state["updated_comment_draft"] = item["comment_draft"]
        _record_action(store, "edit")
        store.state["saved_feedback"] = True
        store.state["version_conflict"] = False
        store.record_activity("更新任务", f"更新「{item['name']}」的协作信息")
        return item

    @app.post("/api/arena/batch")
    async def batch_items(payload: dict[str, Any]) -> dict[str, int]:
        """执行可见的批量优先级、完成或确认删除操作。"""
        ids = payload.get("ids")
        action = payload.get("action")
        if not isinstance(ids, list) or not ids or action not in {"priority", "complete", "delete"}:
            raise HTTPException(status_code=422, detail="批量操作无效")
        selected = [item for item in store.items if item["id"] in ids]
        if not selected:
            raise HTTPException(status_code=404, detail="未找到可操作任务")
        if action == "delete":
            store.undo = {"items": [deepcopy(item) for item in selected], "action": "delete"}
            store.items = [item for item in store.items if item["id"] not in ids]
        elif action == "complete":
            for item in selected:
                item["status"] = "已完成"
                item["updated_at"] = _timestamp()
        else:
            for item in selected:
                item["priority"] = str(payload.get("priority") or "high")
                item["updated_at"] = _timestamp()
        store.state["selected_ids"] = list(ids)
        store.state["batch_action"] = str(action)
        store.state["batch_count"] = len(selected)
        _record_action(store, str(action))
        store.state["undo_available"] = action == "delete"
        store.record_activity("批量操作", f"已对 {len(selected)} 条任务执行{action}")
        return {"updated": len(selected)}

    @app.post("/api/arena/undo")
    async def undo_last_action() -> dict[str, int]:
        """撤销最近一次可撤销的批量删除，并写入可评分反馈。"""
        if store.undo is None or store.undo.get("action") != "delete":
            raise HTTPException(status_code=409, detail="当前没有可撤销的操作")
        restored = list(store.undo["items"])
        store.items = restored + store.items
        store.undo = None
        store.state["undo_available"] = False
        store.state["undo_completed"] = True
        store.record_activity("撤销删除", f"已恢复 {len(restored)} 条任务")
        return {"restored": len(restored)}

    @app.get("/")
    async def home() -> FileResponse:
        """返回构建后的 Vue 入口；构建缺失时给出可诊断错误。"""
        return _frontend_entry(dist_dir)

    @app.get("/arena/{section}")
    async def arena_page(section: str) -> FileResponse:
        """为所有已注册业务路由回退 Vue 入口，拒绝未知页面。"""
        path = f"/arena/{section}"
        if path not in ARENA_ROUTES:
            raise HTTPException(status_code=404, detail="未知评测场页面")
        return _frontend_entry(dist_dir)

    @app.get("/{asset_path:path}")
    async def static_asset(asset_path: str, request: Request) -> FileResponse:
        """返回 Vue 构建资源，阻止路径逃逸和未知资源。"""
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=404, detail="未知接口")
        target = (dist_dir / asset_path).resolve()
        if dist_dir.resolve() not in target.parents or not target.is_file():
            raise HTTPException(status_code=404, detail="前端资源不存在")
        return FileResponse(target)

    return app


def _frontend_entry(dist_dir: Path) -> FileResponse:
    """验证构建入口存在后返回文件，避免运行时依赖 Vite 开发服务器。"""
    entry = dist_dir / "index.html"
    if not entry.is_file():
        raise HTTPException(status_code=503, detail="评测场前端未构建，请先运行 npm run build")
    return FileResponse(entry)


def _find_item(store: BenchmarkStore, item_id: str) -> dict[str, Any]:
    """定位业务任务，未命中时统一返回 HTTP 404。"""
    for item in store.items:
        if item["id"] == item_id:
            return item
    raise HTTPException(status_code=404, detail="任务不存在")


def _record_action(store: BenchmarkStore, action: str) -> None:
    """记录最新可见业务动作，供任务定义选择性断言。"""
    store.state["last_action"] = action


def _matches_version(expected: Any, actual: Any) -> bool:
    """安全比较请求版本，非法版本视为冲突而非泄漏内部异常。"""
    try:
        return int(expected) == int(actual)
    except (TypeError, ValueError):
        return False


def _is_iso_date(value: str) -> bool:
    """检查日期输入是否为稳定的 ISO 日期，空值表示未设置截止日期。"""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _timestamp() -> str:
    """返回展示用 UTC 时间字符串。"""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M")


def _item(
    identifier: str, name: str, owner: str, priority: str, status: str, description: str
) -> dict[str, Any]:
    """构造一条包含工作台全部可见字段的业务任务。"""
    return {
        "id": identifier,
        "name": name,
        "owner": owner,
        "priority": priority,
        "status": status,
        "description": description,
        "updated_at": _timestamp(),
        "project": "北极星"
        if int(identifier) % 4 == 1
        else (
            "曙光" if int(identifier) % 4 == 2 else ("远航" if int(identifier) % 4 == 3 else "云图")
        ),
        "due_date": "2026-09-05",
        "tags": ["协作", "评测"],
        "subtasks": ["确认范围", "同步负责人"],
        "comment_draft": "",
        "version": 1,
    }


_ITEM_STATUSES = {"待处理", "进行中", "已完成", "已逾期"}


def _seed_items() -> list[dict[str, Any]]:
    """返回每题重置时使用的固定工作台数据。"""
    rows = (
        ("支付接口偶发超时", "张三", "high", "已逾期", "北极星项目的线上故障跟踪。"),
        ("移动端登录优化", "李雪", "normal", "待处理", "改进弱网环境下的登录体验。"),
        ("准备灰度发布", "王晨", "high", "进行中", "整理发布清单并确认回滚方案。"),
        ("设计评审", "赵敏", "normal", "待处理", "评审新版工作台交互方案。"),
        ("补充接口文档", "张三", "low", "已完成", "完善开放接口字段说明。"),
        ("核对埋点数据", "王晨", "high", "已逾期", "检查转化漏斗的数据完整性。"),
        ("客户反馈归档", "李雪", "normal", "进行中", "整理本月重点客户反馈。"),
        ("更新隐私说明", "赵敏", "high", "待处理", "同步账号注销相关说明。"),
        ("回归搜索功能", "张三", "normal", "已完成", "验证关键词高亮和空结果页面。"),
        ("整理季度目标", "王晨", "low", "待处理", "汇总团队季度目标与负责人。"),
        ("清理无效邀请", "李雪", "low", "已逾期", "移除超过三十天未接受的邀请。"),
        ("配置异常提醒", "赵敏", "high", "进行中", "为错误率峰值配置通知。"),
    )
    return [_item(str(index), *row) for index, row in enumerate(rows, start=1)]


def _seed_projects() -> list[dict[str, Any]]:
    """返回项目页使用的固定项目卡片。"""
    return [
        {"name": "北极星", "owner": "张三", "progress": 62, "milestones": ["需求冻结", "灰度发布"]},
        {"name": "曙光", "owner": "李雪", "progress": 81, "milestones": ["体验验收", "正式发布"]},
        {"name": "远航", "owner": "王晨", "progress": 45, "milestones": ["联调开始", "风险复盘"]},
        {"name": "云图", "owner": "赵敏", "progress": 93, "milestones": ["数据核验", "归档复盘"]},
    ]


def _seed_members() -> list[dict[str, str]]:
    """返回团队页使用的固定成员数据。"""
    return [
        {"name": "张三", "role": "项目负责人", "workload": "6 项任务"},
        {"name": "李雪", "role": "产品设计", "workload": "4 项任务"},
        {"name": "王晨", "role": "研发工程师", "workload": "7 项任务"},
        {"name": "赵敏", "role": "质量保障", "workload": "5 项任务"},
    ]


def _seed_automations(state: dict[str, Any]) -> list[dict[str, Any]]:
    """根据当前评分状态返回自动化规则及其开关。"""
    rows = (
        ("overdue-reminder", "逾期任务提醒"),
        ("high-priority-notice", "高优先级变更通知"),
        ("daily-summary", "每日进度摘要"),
    )
    return [
        {
            "id": identifier,
            "name": name,
            "enabled": bool(state.get(f"automation_{identifier}", False)),
        }
        for identifier, name in rows
    ]


def _seed_events() -> list[dict[str, str]]:
    """返回日历页使用的固定日期事件。"""
    return [
        {"date": "8 月 27 日", "title": "北极星版本评审", "kind": "评审"},
        {"date": "8 月 28 日", "title": "移动端灰度发布", "kind": "发布"},
        {"date": "8 月 29 日", "title": "季度目标复盘", "kind": "会议"},
    ]


def _seed_activity() -> list[dict[str, str]]:
    """返回重置后可见的本地协作活动时间线。"""
    return [
        {"time": "2026-08-29 09:20", "kind": "风险提醒", "detail": "北极星存在 3 条逾期任务。"},
        {"time": "2026-08-29 09:05", "kind": "项目更新", "detail": "曙光完成体验验收。"},
        {"time": "2026-08-28 18:30", "kind": "协作记录", "detail": "王晨更新了远航的联调计划。"},
    ]
