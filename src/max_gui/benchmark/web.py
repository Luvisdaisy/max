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
        self.items = _seed_items()

    def reset(self, task_id: str) -> BenchmarkTask:
        """将当前任务和业务数据恢复为隔离初始状态。"""
        task = self.tasks[task_id]
        self.current_id = task.id
        self.items = _seed_items()
        self.state = {
            "last_action": "",
            "selected_ids": [],
            "visited_pages": [],
            **deepcopy(task.initial_state),
        }
        return task

    def current(self) -> BenchmarkTask:
        """返回当前任务；未重置时拒绝读取评分状态。"""
        if self.current_id is None:
            raise RuntimeError("尚未重置任务")
        return self.tasks[self.current_id]

    def visible_items(self, query: str, priority: str, sort: str, page: int) -> dict[str, Any]:
        """按可见筛选、排序和分页规则返回工作台数据。"""
        if query:
            self.state["current_query"] = query
        if priority != "all":
            self.state["current_priority"] = priority
        if sort != "updated_desc":
            self.state["current_sort"] = sort
        if page > 1:
            self.state["current_page"] = page
        items = [
            item
            for item in self.items
            if query.lower() in f"{item['name']} {item['owner']}".lower()
        ]
        if priority != "all":
            items = [item for item in items if item["priority"] == priority]
        if sort == "name":
            items.sort(key=lambda item: str(item["name"]))
        else:
            items.sort(key=lambda item: str(item["updated_at"]), reverse=True)
        page_size = 6
        start = max(page - 1, 0) * page_size
        return {
            "items": items[start : start + page_size],
            "page": page,
            "page_size": page_size,
            "total": len(items),
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
        query: str = "", priority: str = "all", sort: str = "updated_desc", page: int = 1
    ) -> dict[str, Any]:
        """返回 Vue 工作台可见的筛选、排序和分页任务列表。"""
        if priority not in {"all", "high", "normal", "low"} or sort not in {"updated_desc", "name"}:
            raise HTTPException(status_code=422, detail="筛选条件无效")
        return store.visible_items(query, priority, sort, page)

    @app.get("/api/arena/summary")
    async def arena_summary() -> dict[str, Any]:
        """返回工作台、报表和团队页面共用的可见聚合数据。"""
        counts = {
            status: sum(item["status"] == status for item in store.items)
            for status in ("待处理", "进行中", "已完成", "已逾期")
        }
        return {
            "counts": counts,
            "projects": _seed_projects(),
            "members": _seed_members(),
            "automations": _seed_automations(store.state),
            "events": _seed_events(),
            "metrics": [
                {"label": "按期完成率", "value": "78%", "detail": "最近 30 天按期完成的任务占比"},
                {"label": "逾期任务最多", "value": "北极星", "detail": "当前共有 3 条逾期任务"},
                {"label": "本周新增任务", "value": "12", "detail": "较上周增加 2 条"},
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
        item = _item(
            str(len(store.items) + 1),
            name,
            owner,
            str(payload.get("priority") or "normal"),
            str(payload.get("status") or "待评测"),
            str(payload.get("description") or ""),
        )
        store.items.insert(0, item)
        store.state["created_name"] = item["name"]
        store.state["created_owner"] = item["owner"]
        store.state["created_priority"] = item["priority"]
        store.state["created_status"] = item["status"]
        _record_action(store, "create")
        return JSONResponse(item, status_code=201)

    @app.put("/api/arena/items/{item_id}")
    async def update_item(item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """更新可见任务字段，找不到目标时返回 404。"""
        item = _find_item(store, item_id)
        for key in ("name", "owner", "priority", "status", "description"):
            if key in payload:
                item[key] = str(payload[key]).strip()
        if not item["name"] or not item["owner"]:
            raise HTTPException(status_code=422, detail="任务名称和负责人不能为空")
        item["updated_at"] = _timestamp()
        store.state["updated_item"] = item["name"]
        store.state["updated_owner"] = item["owner"]
        store.state["updated_priority"] = item["priority"]
        store.state["updated_status"] = item["status"]
        _record_action(store, "edit")
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
        return {"updated": len(selected)}

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


def _timestamp() -> str:
    """返回展示用 UTC 时间字符串。"""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M")


def _item(
    identifier: str, name: str, owner: str, priority: str, status: str, description: str
) -> dict[str, str]:
    """构造一条包含工作台全部可见字段的业务任务。"""
    return {
        "id": identifier,
        "name": name,
        "owner": owner,
        "priority": priority,
        "status": status,
        "description": description,
        "updated_at": _timestamp(),
    }


def _seed_items() -> list[dict[str, str]]:
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
        {"name": "北极星", "owner": "张三", "progress": 62, "overdue": 3},
        {"name": "曙光", "owner": "李雪", "progress": 81, "overdue": 1},
        {"name": "远航", "owner": "王晨", "progress": 45, "overdue": 2},
        {"name": "云图", "owner": "赵敏", "progress": 93, "overdue": 0},
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
