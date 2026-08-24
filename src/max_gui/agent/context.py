"""任务级推理上下文：裁剪模型输入，同时保留会话全量历史。"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, Literal, TypedDict
from uuid import uuid4

RECENT_ACTION_LIMIT = 6
GROUNDED_FACT_LIMIT = 6
GROUNDED_FACT_TEXT_LIMIT = 120
GROUNDED_FACT_SUMMARY_LIMIT = 600


class ActionSummary(TypedDict):
    """一条已完成桌面或观察动作的脱敏摘要。"""

    name: str
    arguments: dict[str, Any]
    outcome: str
    has_observation: bool
    conclusion: str


class GroundedFact(TypedDict):
    """一条绑定截图的短期 GUI 事实，不携带可直接执行的逻辑坐标。"""

    kind: Literal["locate", "cursor_verification"]
    label: str
    status: Literal["valid"]
    source_path: str
    conclusion: str
    target_id: int | None


class TaskContext(TypedDict, total=False):
    """单个用户任务可恢复且可发送给模型的最小语义状态。"""

    task_id: str
    user_instruction: str
    status: str
    plan: list[str]
    current_subtask: str | None
    latest_observation: dict[str, str]
    action_history: list[ActionSummary]
    grounded_facts: list[GroundedFact]


def new_task_context(user_instruction: str, image_paths: Iterable[str] = ()) -> TaskContext:
    """创建一个新任务的初始胶囊。"""
    context: TaskContext = {
        "task_id": f"task-{uuid4().hex}",
        "user_instruction": user_instruction,
        "status": "thinking",
        "plan": [],
        "current_subtask": None,
        "action_history": [],
        "grounded_facts": [],
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
        facts = value.get("grounded_facts")
        context["grounded_facts"] = sanitize_grounded_facts(facts)
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


def replace_locate_facts(
    context: TaskContext, *, items: list[tuple[int, str]], source_path: str
) -> TaskContext:
    """以当前帧成功定位的编号替换旧定位事实。

    参数：
        context: 当前任务胶囊。
        items: 已由可信 `locate` 输出解析的 ``(编号, 标签)``。
        source_path: 当前活动 `ViewFrame` 的截图路径。

    返回：
        带最新有效定位事实的胶囊副本。逻辑坐标不会写入事实。
    """
    facts = [item for item in _grounded_facts(context) if item["kind"] != "locate"]
    for target_id, label in items:
        if len(facts) >= GROUNDED_FACT_LIMIT:
            break
        facts.append(
            {
                "kind": "locate",
                "label": _short_fact_text(label),
                "status": "valid",
                "source_path": source_path,
                "conclusion": "可用 target_id 调用 mouse_move",
                "target_id": target_id,
            }
        )
    return _with_grounded_facts(context, facts)


def clear_grounded_facts(context: TaskContext, *, kinds: set[str] | None = None) -> TaskContext:
    """清除全部或指定种类的短期事实，供截图与动作边界失效旧观察。"""
    if kinds is None:
        return _with_grounded_facts(context, [])
    return _with_grounded_facts(
        context, [item for item in _grounded_facts(context) if item["kind"] not in kinds]
    )


def locate_label(context: TaskContext, *, target_id: int, source_path: str | None) -> str | None:
    """返回当前帧中某定位编号的标签；非当前帧或无效事实返回空。"""
    if not source_path:
        return None
    for item in _grounded_facts(context):
        if (
            item["kind"] == "locate"
            and item["target_id"] == target_id
            and item["source_path"] == source_path
        ):
            return item["label"]
    return None


def record_cursor_verification(
    context: TaskContext, *, label: str, source_path: str
) -> TaskContext:
    """记录移鼠后截图确认的目标，并使旧定位编号失效。"""
    facts = [
        item
        for item in _grounded_facts(context)
        if item["kind"] not in {"locate", "cursor_verification"}
    ]
    facts.append(
        {
            "kind": "cursor_verification",
            "label": _short_fact_text(label),
            "status": "valid",
            "source_path": source_path,
            "conclusion": "已移动并回注截图；确认红十字在目标上后可调用无参数 mouse_click",
            "target_id": None,
        }
    )
    return _with_grounded_facts(context, facts)


def task_context_message(context: TaskContext, *, current_frame_path: str | None = None) -> str:
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
    facts = grounded_facts_message(context, current_frame_path=current_frame_path)
    return (
        f"任务状态：{context.get('status') or 'thinking'}。当前子任务：{current}。"
        f"计划：{plan}。近期动作：{actions}。{latest}。当前有效事实：{facts}。"
    )


def grounded_facts_message(context: TaskContext, *, current_frame_path: str | None) -> str:
    """把当前帧仍有效的事实压缩为模型可读文本，不暴露坐标或原始工具结果。"""
    if not current_frame_path:
        return "无"
    fragments: list[str] = []
    for item in _grounded_facts(context):
        if item["source_path"] != current_frame_path:
            continue
        if item["kind"] == "locate" and item["target_id"] is not None:
            fragments.append(
                f"已定位「{item['label']}」，可用 target_id={item['target_id']} 调用 mouse_move"
            )
        elif item["kind"] == "cursor_verification":
            fragments.append(f"「{item['label']}」已移鼠并回注截图，确认后可无参数 mouse_click")
        if len("；".join(fragments)) >= GROUNDED_FACT_SUMMARY_LIMIT:
            break
    return "；".join(fragments)[:GROUNDED_FACT_SUMMARY_LIMIT] or "无"


def sanitize_grounded_facts(value: Any) -> list[GroundedFact]:
    """过滤持久化事实中的未知或不完整条目，供会话加载与任务恢复共用。"""
    if not isinstance(value, list):
        return []
    restored: list[GroundedFact] = []
    for item in value[-GROUNDED_FACT_LIMIT:]:
        if not isinstance(item, dict):
            continue
        fact = _restore_grounded_fact(item)
        if fact is not None:
            restored.append(fact)
    return restored


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


def _restore_grounded_fact(value: dict[str, Any]) -> GroundedFact | None:
    """把持久化事实收敛为白名单字段；不从历史消息推断可执行编号。"""
    kind = value.get("kind")
    if kind not in {"locate", "cursor_verification"}:
        return None
    label = str(value.get("label") or "").strip()
    source_path = str(value.get("source_path") or "").strip()
    if not label or not source_path or value.get("status") != "valid":
        return None
    target_id: int | None = None
    if kind == "locate":
        try:
            target_id = int(value.get("target_id"))
        except (TypeError, ValueError):
            return None
        if target_id < 1:
            return None
    return {
        "kind": kind,
        "label": _short_fact_text(label),
        "status": "valid",
        "source_path": source_path,
        "conclusion": _short_fact_text(str(value.get("conclusion") or "")),
        "target_id": target_id,
    }


def _grounded_facts(context: TaskContext) -> list[GroundedFact]:
    """返回已恢复的事实副本，避免调用方修改原胶囊。"""
    facts = context.get("grounded_facts")
    if not isinstance(facts, list):
        return []
    return [dict(item) for item in facts if isinstance(item, dict)][-GROUNDED_FACT_LIMIT:]  # type: ignore[return-value]


def _with_grounded_facts(context: TaskContext, facts: list[GroundedFact]) -> TaskContext:
    """复制胶囊并按事实上限写入，确保旧事实不会无限累积。"""
    updated = dict(context)
    updated["grounded_facts"] = facts[-GROUNDED_FACT_LIMIT:]
    return updated


def _short_fact_text(value: str) -> str:
    """裁剪事实展示文本，避免标签或结论膨胀模型上下文。"""
    return value.strip()[:GROUNDED_FACT_TEXT_LIMIT]


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
