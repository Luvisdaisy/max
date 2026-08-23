"""任务级推理上下文：裁剪模型输入，同时保留会话全量历史。"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, TypedDict
from uuid import uuid4

RECENT_ACTION_LIMIT = 6


class ActionSummary(TypedDict):
    """一条已完成桌面或观察动作的脱敏摘要。"""

    name: str
    arguments: dict[str, Any]
    outcome: str
    has_observation: bool
    conclusion: str


class TaskContext(TypedDict, total=False):
    """单个用户任务可恢复且可发送给模型的最小语义状态。"""

    task_id: str
    user_instruction: str
    status: str
    plan: list[str]
    current_subtask: str | None
    latest_observation: dict[str, str]
    action_history: list[ActionSummary]


def new_task_context(user_instruction: str, image_paths: Iterable[str] = ()) -> TaskContext:
    """创建一个新任务的初始胶囊。"""
    context: TaskContext = {
        "task_id": f"task-{uuid4().hex}",
        "user_instruction": user_instruction,
        "status": "thinking",
        "plan": [],
        "current_subtask": None,
        "action_history": [],
    }
    paths = list(image_paths)
    if paths:
        context["latest_observation"] = {"path": paths[-1], "source": "user_attachment"}
    return context


def restore_task_context(value: Any, messages: list[dict[str, Any]]) -> TaskContext:
    """恢复持久化胶囊；旧 checkpoint 缺字段时从当前任务消息安全降级。"""
    if isinstance(value, dict) and value.get("task_id") and value.get("user_instruction"):
        context = new_task_context(str(value["user_instruction"]))
        context["task_id"] = str(value["task_id"])
        context["status"] = str(value.get("status") or "thinking")
        context["plan"] = [str(item) for item in value.get("plan") or []]
        raw_current = value.get("current_subtask")
        context["current_subtask"] = None if raw_current is None else str(raw_current)
        observation = value.get("latest_observation")
        if isinstance(observation, dict) and observation.get("path"):
            context["latest_observation"] = {
                "path": str(observation["path"]),
                "source": str(observation.get("source") or "tool"),
            }
        history = value.get("action_history")
        if isinstance(history, list):
            context["action_history"] = [
                _restore_action(item)
                for item in history[-RECENT_ACTION_LIMIT:]
                if isinstance(item, dict)
            ]
        return context
    return new_task_context(_first_user_instruction(messages))


def update_task_context(
    context: TaskContext, *, status: str, plan: list[str], current_subtask: str | None
) -> TaskContext:
    """返回带最新运行状态和计划的胶囊副本。"""
    updated = dict(context)
    updated["status"] = status
    updated["plan"] = list(plan)
    updated["current_subtask"] = current_subtask
    return updated


def append_action_summary(
    context: TaskContext,
    *,
    name: str,
    arguments: Any,
    error: str | None,
    has_observation: bool,
    conclusion: str,
    image_path: str | None,
) -> TaskContext:
    """追加脱敏动作摘要，并在有新图时覆盖最新观察。"""
    updated = dict(context)
    history = list(context.get("action_history") or [])
    history.append(
        {
            "name": name,
            "arguments": _safe_arguments(name, arguments),
            "outcome": "failed" if error else "success",
            "has_observation": has_observation,
            "conclusion": conclusion[:400],
        }
    )
    updated["action_history"] = history[-RECENT_ACTION_LIMIT:]
    if image_path:
        updated["latest_observation"] = {"path": image_path, "source": "tool"}
    return updated


def latest_observation_path(context: TaskContext) -> str | None:
    """返回胶囊选择的最新观察路径；缺失时返回 `None`。"""
    observation = context.get("latest_observation")
    if not isinstance(observation, dict):
        return None
    path = observation.get("path")
    return str(path) if path else None


def task_context_message(context: TaskContext) -> str:
    """生成不含敏感正文的简短任务状态文本，供模型理解当前执行位置。"""
    current = context.get("current_subtask") or "未指定"
    plan = "；".join(context.get("plan") or [])[:600] or "未指定"
    latest = "有最新观察" if latest_observation_path(context) else "尚无有效观察"
    actions = (
        "；".join(
            f"{item['name']}（{item['outcome']}）" for item in context.get("action_history") or []
        )
        or "无"
    )
    return (
        f"任务状态：{context.get('status') or 'thinking'}。当前子任务：{current}。"
        f"计划：{plan}。近期动作：{actions}。{latest}。"
    )


def _first_user_instruction(messages: list[dict[str, Any]]) -> str:
    """从旧状态提取首条用户文本；无法取得时返回兼容占位说明。"""
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, dict):
            return str(content.get("text") or "继续当前任务")
        return str(content or "继续当前任务")
    return "继续当前任务"


def _restore_action(value: dict[str, Any]) -> ActionSummary:
    """把持久化动作收敛为已知的安全字段。"""
    arguments = value.get("arguments")
    return {
        "name": str(value.get("name") or "unknown"),
        "arguments": dict(arguments) if isinstance(arguments, dict) else {},
        "outcome": str(value.get("outcome") or "success"),
        "has_observation": bool(value.get("has_observation")),
        "conclusion": str(value.get("conclusion") or "")[:400],
    }


def _safe_arguments(name: str, arguments: Any) -> dict[str, Any]:
    """脱敏并截断工具参数，确保任务摘要不会保存输入正文。"""
    parsed = _parse_arguments(arguments)
    if name == "keyboard_type":
        return {"text_chars": len(str(parsed.get("text") or ""))}
    encoded = json.dumps(parsed, ensure_ascii=False, default=str)
    if len(encoded) <= 400:
        return parsed
    return {"truncated": encoded[:400]}


def _parse_arguments(arguments: Any) -> dict[str, Any]:
    """将工具参数转为字典；无法解析时不保留原始长文本。"""
    if isinstance(arguments, dict):
        return dict(arguments)
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {"raw_chars": len(arguments)}
        return dict(parsed) if isinstance(parsed, dict) else {"value": str(parsed)[:200]}
    return {}
