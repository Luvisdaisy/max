"""任务级推理上下文：裁剪模型输入，同时保留会话全量历史。"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal, TypedDict
from uuid import uuid4

RECENT_ACTION_LIMIT = 6
GROUNDED_FACT_LIMIT = 6
GROUNDED_FACT_TEXT_LIMIT = 120
GROUNDED_FACT_SUMMARY_LIMIT = 600
UI_ELEMENT_LIMIT = 8
PROGRESS_LIMIT = 12

ExpectationKind = Literal[
    "dialog_appears",
    "active_window_changes",
    "element_appears",
    "element_disappears",
    "element_selected",
    "screen_changed",
]
ProgressStatus = Literal["pending", "in_progress", "verified", "blocked"]


class DesktopIdentity(TypedDict):
    """只读桌面身份；未知字段用 `None`，绝不由视觉推测补写。"""

    id: str | None
    name: str | None
    role: str | None


class UIElementCandidate(TypedDict):
    """与单张观察帧绑定的非执行性 UI 候选。"""

    id: str
    label: str
    role: str | None
    source: str
    clickable: bool
    editable: bool


class DesktopSnapshot(TypedDict):
    """当前观察帧上的轻量桌面状态，不能作为坐标或输入授权。"""

    frame_path: str
    captured_at: str
    active_app: DesktopIdentity
    active_window: DesktopIdentity
    focused_element: DesktopIdentity
    active_dialog: DesktopIdentity
    ui_elements: list[UIElementCandidate]
    observation_status: str


class ProgressItem(TypedDict):
    """一项可验证的任务进度。"""

    id: str
    label: str
    status: ProgressStatus
    required: bool


class ActionExpectation(TypedDict):
    """一次桌面副作用后的受限、可确定性验证预期。"""

    kind: ExpectationKind
    target: str | None
    progress_id: str | None
    source_frame_path: str
    conclusion: str


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
    completion_required: bool
    completion_verified: bool
    completion_summary: str
    conversation_observation: dict[str, str]
    conversation_dialogue: list[str]
    recovery: dict[str, Any]
    completion_declaration: dict[str, Any]
    completion_verification: dict[str, Any]
    desktop_snapshot: DesktopSnapshot
    progress: list[ProgressItem]
    current_expectation: ActionExpectation
    ui_snapshot: dict[str, Any]


def new_task_context(
    user_instruction: str,
    image_paths: Iterable[str] = (),
    conversation_context: dict[str, Any] | None = None,
) -> TaskContext:
    """创建一个新任务的初始胶囊。"""
    context: TaskContext = {
        "task_id": f"task-{uuid4().hex}",
        "user_instruction": user_instruction,
        "status": "thinking",
        "plan": [],
        "current_subtask": None,
        "action_history": [],
        "grounded_facts": [],
        "completion_required": False,
        "completion_verified": False,
        "completion_summary": "",
        "recovery": {
            "failure_fingerprint": None,
            "failure_count": 0,
            "frame_path": None,
            "blocked_calls": [],
            "recovery_hint": None,
        },
        "completion_declaration": {},
        "completion_verification": {},
        "progress": [],
    }
    paths = list(image_paths)
    if paths:
        context["latest_observation"] = {"path": paths[-1], "source": "user_attachment"}
    observation = (conversation_context or {}).get("observation")
    if isinstance(observation, dict) and observation.get("path"):
        context["conversation_observation"] = {
            "path": str(observation["path"]),
            "source": str(observation.get("source") or "tool"),
        }
    dialogue = (conversation_context or {}).get("dialogue")
    if isinstance(dialogue, list):
        context["conversation_dialogue"] = [str(item)[:240] for item in dialogue][-2:]
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
        context["completion_required"] = bool(value.get("completion_required"))
        context["completion_verified"] = bool(value.get("completion_verified"))
        context["completion_summary"] = str(value.get("completion_summary") or "")[:400]
        recovery = value.get("recovery")
        if isinstance(recovery, dict):
            context["recovery"] = _restore_recovery(recovery)
        declaration = value.get("completion_declaration")
        if isinstance(declaration, dict):
            context["completion_declaration"] = _restore_completion_declaration(declaration)
        verification = value.get("completion_verification")
        if isinstance(verification, dict):
            context["completion_verification"] = _restore_completion_verification(verification)
        snapshot = sanitize_desktop_snapshot(value.get("desktop_snapshot"))
        if snapshot is not None:
            context["desktop_snapshot"] = snapshot
        context["progress"] = sanitize_progress(value.get("progress"))
        expectation = sanitize_expectation(value.get("current_expectation"))
        if expectation is not None:
            context["current_expectation"] = expectation
        ui_snapshot = sanitize_ui_snapshot(value.get("ui_snapshot"))
        if ui_snapshot is not None:
            context["ui_snapshot"] = ui_snapshot
        observation = value.get("conversation_observation")
        if isinstance(observation, dict) and observation.get("path"):
            context["conversation_observation"] = {
                "path": str(observation["path"]),
                "source": str(observation.get("source") or "tool"),
            }
        dialogue = value.get("conversation_dialogue")
        if isinstance(dialogue, list):
            context["conversation_dialogue"] = [str(item)[:240] for item in dialogue][-2:]
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


def replace_desktop_snapshot(
    context: TaskContext, *, frame_path: str, observation: Any
) -> TaskContext:
    """以当前帧的只读观察替换桌面快照，并失效上一帧候选与预期。

    参数：
        context: 当前任务胶囊。
        frame_path: 已成功写入的当前观察帧路径。
        observation: 平台观察适配器的字典结果；坏字段安全降级为未知。

    返回：
        绑定新帧的胶囊副本。待验证预期会保留，供 `observe` 对动作前后两帧进行核验。
    """
    updated = dict(context)
    raw = observation if isinstance(observation, dict) else {}
    snapshot: DesktopSnapshot = {
        "frame_path": str(frame_path),
        "captured_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "active_app": _identity(raw.get("active_app")),
        "active_window": _identity(raw.get("active_window")),
        "focused_element": _identity(raw.get("focused_element")),
        "active_dialog": _identity(raw.get("active_dialog")),
        "ui_elements": [],
        "observation_status": str(raw.get("observation_status") or "unknown")[:80],
    }
    updated["desktop_snapshot"] = snapshot
    updated.pop("ui_snapshot", None)
    return updated


def replace_ui_snapshot(context: TaskContext, summary: Any) -> TaskContext:
    """写入当前 UI 快照的脱敏摘要，并让新版本取代旧元素引用。

    参数：`summary` 仅可来自 `UISnapshot.summary()`；坏数据会清空旧摘要。
    返回：带当前版本、上下文和有限元素标签的胶囊副本。
    """
    updated = dict(context)
    cleaned = sanitize_ui_snapshot(summary)
    if cleaned is None:
        updated.pop("ui_snapshot", None)
    else:
        updated["ui_snapshot"] = cleaned
    return updated


def add_ui_candidates(
    context: TaskContext, *, frame_path: str, candidates: Any, source: str
) -> TaskContext:
    """把当前帧唯一可信的语义候选加入快照，不保留坐标或定位编号。"""
    updated = dict(context)
    snapshot = sanitize_desktop_snapshot(context.get("desktop_snapshot"))
    if (
        snapshot is None
        or snapshot["frame_path"] != str(frame_path)
        or not isinstance(candidates, list)
    ):
        return updated
    items = list(snapshot["ui_elements"])
    for index, raw in enumerate(candidates):
        if len(items) >= UI_ELEMENT_LIMIT or not isinstance(raw, dict):
            break
        label = str(raw.get("label") or raw.get("text") or "").strip()
        if not label:
            continue
        role = str(raw.get("role") or "").strip() or None
        item = {
            "id": f"{source}-{index + 1}",
            "label": label[:120],
            "role": role[:60] if role else None,
            "source": source[:40],
            "clickable": bool(raw.get("clickable", True)),
            "editable": bool(raw.get("editable", False)),
        }
        if not any(
            existing["label"] == item["label"] and existing["role"] == item["role"]
            for existing in items
        ):
            items.append(item)
    snapshot["ui_elements"] = items[:UI_ELEMENT_LIMIT]
    updated["desktop_snapshot"] = snapshot
    return updated


def register_expectation(
    context: TaskContext, value: Any, *, source_frame_path: str | None
) -> TaskContext:
    """登记模型随副作用提交的受限预期；非法输入只写入恢复提示。"""
    updated = dict(context)
    if not isinstance(value, dict) or not source_frame_path:
        return updated
    kind = str(value.get("kind") or "")
    if kind not in {
        "dialog_appears",
        "active_window_changes",
        "element_appears",
        "element_disappears",
        "element_selected",
        "screen_changed",
    }:
        return updated
    target = str(value.get("target") or "").strip() or None
    progress_id = str(value.get("progress_id") or "").strip() or None
    updated["current_expectation"] = {
        "kind": kind,  # type: ignore[typeddict-item]
        "target": target[:120] if target else None,
        "progress_id": progress_id[:80] if progress_id else None,
        "source_frame_path": str(source_frame_path),
        "conclusion": "等待动作后的独立观察",
    }
    if progress_id:
        updated["progress"] = _ensure_progress_item(context.get("progress"), progress_id, target)
    return updated


def verify_current_expectation(
    context: TaskContext, *, previous_frame_path: str | None
) -> TaskContext:
    """用当前快照与预期来源帧确定性验证动作效果，并只在成功时推进进度。"""
    updated = dict(context)
    expectation = sanitize_expectation(context.get("current_expectation"))
    snapshot = sanitize_desktop_snapshot(context.get("desktop_snapshot"))
    if expectation is None or snapshot is None:
        return updated
    if (
        expectation["source_frame_path"] == snapshot["frame_path"]
        or previous_frame_path != expectation["source_frame_path"]
    ):
        expectation["conclusion"] = "缺少动作前后不同观察帧，无法验证预期"
        updated["current_expectation"] = expectation
        return updated
    kind = expectation["kind"]
    target = (expectation["target"] or "").casefold()
    candidates = snapshot["ui_elements"]
    labels = [item["label"].casefold() for item in candidates]
    if kind == "dialog_appears":
        observed = snapshot["active_dialog"]["name"] or ""
        ok = bool(observed and (not target or target in observed.casefold()))
    elif kind == "active_window_changes":
        ok = snapshot["active_window"]["id"] is not None
    elif kind == "element_appears":
        ok = bool(target and any(target in label for label in labels))
    elif kind == "element_disappears":
        ok = bool(target and not any(target in label for label in labels))
    elif kind == "element_selected":
        focused = snapshot["focused_element"]["name"] or ""
        ok = bool(target and target in focused.casefold())
    else:
        ok = True
    if ok:
        progress_id = expectation["progress_id"]
        if progress_id:
            updated["progress"] = _mark_progress(context.get("progress"), progress_id, "verified")
        updated.pop("current_expectation", None)
    else:
        expectation["conclusion"] = "后置观察未确认预期，进度未推进"
        updated["current_expectation"] = expectation
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


def conversation_observation_path(context: TaskContext) -> str | None:
    """返回只读历史观察路径；它绝不代表当前可执行截图。"""
    observation = context.get("conversation_observation")
    if not isinstance(observation, dict):
        return None
    path = observation.get("path")
    return str(path) if path else None


def require_completion(context: TaskContext) -> TaskContext:
    """标记副作用任务需要显式完成声明，并清除旧的通过状态。"""
    updated = dict(context)
    updated["completion_required"] = True
    updated["completion_verified"] = False
    updated["completion_summary"] = ""
    updated["completion_declaration"] = {}
    updated["completion_verification"] = {}
    return updated


def register_completion_declaration(
    context: TaskContext, *, summary: str, evidence: str, observed_path: str | None
) -> TaskContext:
    """登记待验证完成声明，不改变完成状态。"""
    updated = dict(context)
    updated["completion_required"] = True
    updated["completion_verified"] = False
    updated["completion_summary"] = summary.strip()[:400]
    updated["completion_declaration"] = {
        "summary": summary.strip()[:400],
        "evidence": evidence.strip()[:400],
        "declared_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "before_observation": observed_path,
    }
    updated["completion_verification"] = {}
    return updated


def verify_completion(
    context: TaskContext, *, summary: str, observation_path: str | None = None
) -> TaskContext:
    """记录独立后置观察的验证结论并迁移到完成状态。"""
    updated = dict(context)
    updated["completion_required"] = True
    updated["completion_verified"] = True
    updated["completion_summary"] = summary.strip()[:400]
    updated["completion_verification"] = {
        "ok": True,
        "observation_path": observation_path,
        "conclusion": summary.strip()[:400],
    }
    return updated


def update_recovery(
    context: TaskContext,
    *,
    fingerprint: str | None,
    frame_path: str | None,
    hint: str | None,
    blocked_calls: list[str] | None = None,
    increment: bool = True,
) -> TaskContext:
    """更新当前帧的失败指纹与恢复建议；成功观察会传入空指纹清零。"""
    updated = dict(context)
    previous = context.get("recovery") if isinstance(context.get("recovery"), dict) else {}
    same = (
        fingerprint is not None
        and previous.get("failure_fingerprint") == fingerprint
        and previous.get("frame_path") == frame_path
    )
    count = int(previous.get("failure_count") or 0) + (1 if increment and same else 0)
    if fingerprint is None:
        count = 0
    elif not same:
        count = 1
    updated["recovery"] = {
        "failure_fingerprint": fingerprint,
        "failure_count": count,
        "frame_path": frame_path,
        "blocked_calls": list(blocked_calls or previous.get("blocked_calls") or []),
        "recovery_hint": hint,
    }
    return updated


def _restore_recovery(value: dict[str, Any]) -> dict[str, Any]:
    """清洗恢复信号，避免坏 checkpoint 注入不可序列化值。"""
    return {
        "failure_fingerprint": str(value.get("failure_fingerprint"))
        if value.get("failure_fingerprint")
        else None,
        "failure_count": max(0, int(value.get("failure_count") or 0)),
        "frame_path": str(value.get("frame_path")) if value.get("frame_path") else None,
        "blocked_calls": [str(item) for item in value.get("blocked_calls") or []][:12],
        "recovery_hint": str(value.get("recovery_hint"))[:400]
        if value.get("recovery_hint")
        else None,
    }


def _restore_completion_declaration(value: dict[str, Any]) -> dict[str, Any]:
    """清洗待验证完成声明。"""
    return {
        "summary": str(value.get("summary") or "")[:400],
        "evidence": str(value.get("evidence") or "")[:400],
        "declared_at": str(value.get("declared_at") or ""),
        "before_observation": str(value.get("before_observation"))
        if value.get("before_observation")
        else None,
    }


def _restore_completion_verification(value: dict[str, Any]) -> dict[str, Any]:
    """清洗完成核验结论。"""
    return {
        "ok": bool(value.get("ok")),
        "observation_path": str(value.get("observation_path"))
        if value.get("observation_path")
        else None,
        "conclusion": str(value.get("conclusion") or "")[:400],
    }


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
    history_path = conversation_observation_path(context)
    history = "无"
    if history_path:
        history = "有一张仅供理解的历史观察；不得用它的坐标、编号或界面状态执行桌面动作"
    actions = (
        "；".join(
            f"{item['name']}（{item['outcome']}）" for item in context.get("action_history") or []
        )
        or "无"
    )
    facts = grounded_facts_message(context, current_frame_path=current_frame_path)
    recovery = context.get("recovery") or {}
    recovery_text = str(recovery.get("recovery_hint") or "")
    if recovery_text:
        recovery_text = (
            f"恢复护栏：{recovery_text}（连续 {int(recovery.get('failure_count') or 0)} 次）"
        )
    if context.get("completion_verified"):
        completion = "已通过 task_complete 完成验证"
    elif context.get("completion_required"):
        completion = (
            "副作用后仍需完成验证；确认最新截图达到目标后调用 task_complete，不要只返回正文"
        )
    else:
        completion = "当前未要求副作用完成声明"
    snapshot = sanitize_desktop_snapshot(context.get("desktop_snapshot"))
    desktop = "当前桌面状态未知"
    if snapshot is not None and snapshot["frame_path"] == current_frame_path:
        app = snapshot["active_app"]["name"] or "未知应用"
        window = snapshot["active_window"]["name"] or "未知窗口"
        dialog = snapshot["active_dialog"]["name"] or "无已知弹窗"
        desktop = f"当前桌面：{app}／{window}；弹窗：{dialog}"
    ui_snapshot = sanitize_ui_snapshot(context.get("ui_snapshot"))
    ui_text = "无结构化 UI 快照"
    if ui_snapshot is not None and ui_snapshot["frame_path"] == current_frame_path:
        labels = "；".join(
            f"{item['id']} {item['role']}「{item['label']}」" for item in ui_snapshot["elements"]
        )
        ui_text = (
            f"UI 快照 v{ui_snapshot['version']}（{ui_snapshot['context']}）：{labels or '无元素'}。"
            "语义动作必须携带 element_id 与 ui_version，不能传坐标或 locator"
        )
    progress = (
        "；".join(
            f"{item['label']}（{item['status']}）"
            for item in sanitize_progress(context.get("progress"))
        )
        or "无"
    )
    expectation = sanitize_expectation(context.get("current_expectation"))
    expectation_text = "无待验证预期"
    if expectation is not None:
        expectation_text = f"待验证：{expectation['kind']}（{expectation['conclusion']}）"
    return (
        f"任务状态：{context.get('status') or 'thinking'}。当前子任务：{current}。"
        f"计划：{plan}。近期动作：{actions}。{latest}。历史观察：{history}。当前有效事实：{facts}。{recovery_text}。"
        f"{desktop}。{ui_text}。进度：{progress}。{expectation_text}。完成门：{completion}。"
    )


def grounded_facts_message(context: TaskContext, *, current_frame_path: str | None) -> str:
    """把当前帧仍有效的事实压缩为模型可读文本，不暴露坐标或原始工具结果。"""
    if not current_frame_path:
        return "无"
    fragments: list[str] = []
    for item in _grounded_facts(context):
        if item["source_path"] != current_frame_path:
            continue
        if item["kind"] == "cursor_verification":
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


def sanitize_desktop_snapshot(value: Any) -> DesktopSnapshot | None:
    """清洗持久化桌面快照；坏字段降级为未知，候选不保留坐标。"""
    if not isinstance(value, dict) or not value.get("frame_path"):
        return None
    items: list[UIElementCandidate] = []
    for raw in value.get("ui_elements") or []:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or "").strip()
        item_id = str(raw.get("id") or "").strip()
        if not label or not item_id:
            continue
        items.append(
            {
                "id": item_id[:80],
                "label": label[:120],
                "role": str(raw.get("role") or "").strip()[:60] or None,
                "source": str(raw.get("source") or "unknown")[:40],
                "clickable": bool(raw.get("clickable")),
                "editable": bool(raw.get("editable")),
            }
        )
        if len(items) >= UI_ELEMENT_LIMIT:
            break
    return {
        "frame_path": str(value["frame_path"]),
        "captured_at": str(value.get("captured_at") or "")[:80],
        "active_app": _identity(value.get("active_app")),
        "active_window": _identity(value.get("active_window")),
        "focused_element": _identity(value.get("focused_element")),
        "active_dialog": _identity(value.get("active_dialog")),
        "ui_elements": items,
        "observation_status": str(value.get("observation_status") or "unknown")[:80],
    }


def sanitize_ui_snapshot(value: Any) -> dict[str, Any] | None:
    """清洗可持久化 UI 摘要，删除 locator、坐标和不支持的后端字段。"""
    if not isinstance(value, dict):
        return None
    try:
        version = int(value.get("version"))
    except (TypeError, ValueError):
        return None
    frame_path = str(value.get("frame_path") or "").strip()
    context = str(value.get("context") or "")
    if version < 1 or not frame_path or context not in {"browser", "native", "vision"}:
        return None
    elements: list[dict[str, Any]] = []
    for raw in value.get("elements") or []:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        label = str(raw.get("label") or "").strip()
        backend = str(raw.get("backend") or "")
        if not item_id or not label or backend not in {"browser", "macos_ax", "vision"}:
            continue
        elements.append(
            {
                "id": item_id[:40],
                "role": str(raw.get("role") or "unknown")[:60],
                "label": label[:120],
                "clickable": bool(raw.get("clickable")),
                "editable": bool(raw.get("editable")),
                "backend": backend,
            }
        )
        if len(elements) >= UI_ELEMENT_LIMIT:
            break
    return {
        "version": version,
        "frame_path": frame_path,
        "context": context,
        "url": str(value.get("url"))[:200] if value.get("url") else None,
        "elements": elements,
    }


def sanitize_progress(value: Any) -> list[ProgressItem]:
    """只恢复有限且枚举合法的进度项。"""
    if not isinstance(value, list):
        return []
    items: list[ProgressItem] = []
    for raw in value[-PROGRESS_LIMIT:]:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        label = str(raw.get("label") or "").strip()
        status = str(raw.get("status") or "pending")
        if (
            not item_id
            or not label
            or status not in {"pending", "in_progress", "verified", "blocked"}
        ):
            continue
        items.append(
            {
                "id": item_id[:80],
                "label": label[:120],
                "status": status,  # type: ignore[typeddict-item]
                "required": bool(raw.get("required")),
            }
        )
    return items


def sanitize_expectation(value: Any) -> ActionExpectation | None:
    """恢复受限 expectation；未知类型不可进入后续验证。"""
    if not isinstance(value, dict):
        return None
    kind = str(value.get("kind") or "")
    frame = str(value.get("source_frame_path") or "").strip()
    if (
        kind
        not in {
            "dialog_appears",
            "active_window_changes",
            "element_appears",
            "element_disappears",
            "element_selected",
            "screen_changed",
        }
        or not frame
    ):
        return None
    return {
        "kind": kind,  # type: ignore[typeddict-item]
        "target": str(value.get("target") or "").strip()[:120] or None,
        "progress_id": str(value.get("progress_id") or "").strip()[:80] or None,
        "source_frame_path": frame,
        "conclusion": str(value.get("conclusion") or "")[:240],
    }


def _identity(value: Any) -> DesktopIdentity:
    """将平台观察结果收敛为可持久化的非敏感身份摘要。"""
    raw = value if isinstance(value, dict) else {}
    return {
        "id": str(raw.get("id") or "").strip()[:120] or None,
        "name": str(raw.get("name") or "").strip()[:120] or None,
        "role": str(raw.get("role") or "").strip()[:60] or None,
    }


def _ensure_progress_item(value: Any, item_id: str, label: str | None) -> list[ProgressItem]:
    """按 ID 复用进度项，缺失时创建进行中项。"""
    items = sanitize_progress(value)
    if any(item["id"] == item_id for item in items):
        return items
    items.append(
        {
            "id": item_id[:80],
            "label": (label or item_id)[:120],
            "status": "in_progress",
            "required": True,
        }
    )
    return items[-PROGRESS_LIMIT:]


def _mark_progress(value: Any, item_id: str, status: ProgressStatus) -> list[ProgressItem]:
    """返回指定项更新后的进度列表；不存在的 ID 保持原样。"""
    result = sanitize_progress(value)
    for item in result:
        if item["id"] == item_id:
            item["status"] = status
    return result


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
