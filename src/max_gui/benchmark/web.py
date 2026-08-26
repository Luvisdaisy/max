"""受控本地 Web 测试场。

页面只呈现普通业务 UI；重置和状态接口由评测运行器调用，未向 Agent 页面公开。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from max_gui.benchmark.tasks import BenchmarkTask, TaskSuite


class BenchmarkStore:
    """按当前任务保存隔离业务状态。"""

    def __init__(self, suite: TaskSuite) -> None:
        """记录任务索引并初始化为空状态。"""
        self.tasks = {task.id: task for task in suite.tasks}
        self.current_id: str | None = None
        self.state: dict[str, Any] = {}

    def reset(self, task_id: str) -> BenchmarkTask:
        """恢复任务初始状态，未知任务抛出 KeyError。"""
        task = self.tasks[task_id]
        self.current_id = task.id
        self.state = {
            "saved": False,
            "priority": "normal",
            "dark_mode": False,
            "notifications": True,
            "query": "",
            "sort": "date",
            "selected": "",
            "project_name": "",
            "error": "",
            **deepcopy(task.initial_state),
        }
        return task

    def current(self) -> BenchmarkTask:
        """返回当前任务；尚未重置时抛出 RuntimeError。"""
        if self.current_id is None:
            raise RuntimeError("尚未重置任务")
        return self.tasks[self.current_id]


def create_benchmark_app(suite: TaskSuite) -> FastAPI:
    """创建只供本地评测启动的 FastAPI 应用。"""
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    store = BenchmarkStore(suite)
    app.state.benchmark_store = store

    @app.post("/api/reset")
    async def reset(payload: dict[str, str]) -> dict[str, Any]:
        """按任务标识重置测试状态。"""
        try:
            task = store.reset(payload["task_id"])
        except (KeyError, TypeError) as exc:
            raise HTTPException(status_code=404, detail="未知任务") from exc
        return {"task_id": task.id, "route": task.route}

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        """返回评测器判分所需的最小状态。"""
        try:
            store.current()
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return dict(store.state)

    @app.get("/form", response_class=HTMLResponse)
    async def form_page() -> str:
        """渲染项目表单。"""
        return _page("项目表单", _form_body(store.state))

    @app.post("/form/save")
    async def save_form(name: str = Form(""), priority: str = Form("normal")) -> RedirectResponse:
        """保存项目；空名称展示可见校验错误。"""
        store.state["project_name"] = name.strip()
        store.state["priority"] = priority
        store.state["error"] = "项目名称不能为空" if not name.strip() else ""
        store.state["saved"] = bool(name.strip())
        return RedirectResponse("/form", status_code=303)

    @app.get("/files", response_class=HTMLResponse)
    async def files_page() -> str:
        """渲染本地模拟文件列表。"""
        return _page("文件列表", _files_body(store.state))

    @app.post("/files/update")
    async def update_files(
        query: str = Form(""), sort: str = Form("date"), selected: str = Form("")
    ) -> RedirectResponse:
        """保存搜索、排序或选择结果。"""
        store.state.update(query=query.strip(), sort=sort, selected=selected)
        return RedirectResponse("/files", status_code=303)

    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page() -> str:
        """渲染开关、确认与保存页面。"""
        return _page("设置", _settings_body(store.state))

    @app.post("/settings/save")
    async def save_settings(
        dark_mode: str | None = Form(None),
        notifications: str | None = Form(None),
        confirm: str | None = Form(None),
    ) -> RedirectResponse:
        """保存设置；需要确认时，未确认不写入保存状态。"""
        store.state["dark_mode"] = dark_mode == "on"
        store.state["notifications"] = notifications == "on"
        store.state["saved"] = not store.state.get("confirm_required") or confirm == "yes"
        return RedirectResponse("/settings", status_code=303)

    return app


def _page(title: str, body: str) -> str:
    """返回固定尺寸、可供截图识别的中文页面壳。"""
    return f"""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>{title}</title>
<style>body{{font:18px -apple-system;margin:48px;max-width:900px}}input,select,button{{font:18px;padding:10px;margin:8px 0}}button{{cursor:pointer}}.error{{color:#b42318}}</style><main><h1>{title}</h1>{body}</main></html>"""


def _form_body(state: dict[str, Any]) -> str:
    """构造项目表单 HTML。"""
    error = f"<p class='error'>{state['error']}</p>" if state["error"] else ""
    return f"""{error}<form method='post' action='/form/save'><label>项目名称<br><input name='name' value='{state["project_name"]}'></label><br><label>优先级<br><select name='priority'><option value='normal'>普通</option><option value='high'>高</option></select></label><br><button>保存</button></form>"""


def _files_body(state: dict[str, Any]) -> str:
    """构造可滚动的文件列表 HTML。"""
    items = ["report.pdf", "plan.md", "notes.txt", "archive.zip"] * 8
    rows = "".join(f"<option>{item}</option>" for item in items)
    return f"""<form method='post' action='/files/update'><label>搜索<br><input name='query' value='{state["query"]}'></label><br><label>排序<select name='sort'><option value='date'>日期</option><option value='name'>名称</option></select></label><br><label>选择<select name='selected' size='8'>{rows}</select></label><br><button>应用</button></form>"""


def _settings_body(state: dict[str, Any]) -> str:
    """构造设置与可选确认控件 HTML。"""
    confirm = (
        "<label><input type='checkbox' name='confirm' value='yes'>我确认</label><br>"
        if state.get("confirm_required")
        else ""
    )
    return f"""<form method='post' action='/settings/save'><label><input type='checkbox' name='dark_mode' {"checked" if state["dark_mode"] else ""}>深色模式</label><br><label><input type='checkbox' name='notifications' {"checked" if state["notifications"] else ""}>开启通知</label><br>{confirm}<button>保存设置</button></form>"""
