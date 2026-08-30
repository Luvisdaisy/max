"""Online-Mind2Web 任务和安全清单的严格本地加载。

加载过程只读取调用方明确指定的本地 JSON 文件；不触发远程下载、不接受数据集条款，也不访问网页。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from max_gui.mind2web.models import OnlineMind2WebTask, SafetyManifest, SafetyRule


def load_tasks(path: Path, *, authorized_root: Path) -> tuple[tuple[OnlineMind2WebTask, ...], str]:
    """读取显式授权的任务文件并返回任务与 SHA-256 摘要。

    参数：`path` 为用户提供的 JSON；`authorized_root` 限制文件及其解析路径必须位于该目录内。
    返回：不可变任务元组与源文件内容摘要。
    异常：路径越界、JSON 非法、字段不完整或任务标识重复时抛出 `ValueError`。
    """
    resolved = _authorized_file(path, authorized_root)
    raw_bytes = resolved.read_bytes()
    try:
        raw = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError("Online-Mind2Web 任务文件不是合法 JSON") from exc
    entries = raw.get("tasks") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        raise ValueError("任务文件必须是任务数组或含 tasks 数组的对象")
    tasks = tuple(_task_from_raw(item) for item in entries)
    if len({task.task_id for task in tasks}) != len(tasks):
        raise ValueError("Online-Mind2Web task_id 不得重复")
    return tasks, hashlib.sha256(raw_bytes).hexdigest()


def load_safety_manifest(path: Path, *, authorized_root: Path) -> tuple[SafetyManifest, str]:
    """读取用户显式批准的安全清单。

    清单中输入白名单是评测导出的最小允许集合，不能通过缺省值放开。
    """
    resolved = _authorized_file(path, authorized_root)
    raw_bytes = resolved.read_bytes()
    try:
        raw = json.loads(raw_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError("安全清单不是合法 JSON") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("rules"), list):
        raise ValueError("安全清单必须包含 rules 数组")
    rules = tuple(_rule_from_raw(item) for item in raw["rules"])
    if len({rule.task_id for rule in rules}) != len(rules):
        raise ValueError("安全清单 task_id 不得重复")
    return (
        SafetyManifest(name=str(raw.get("name") or "online-mind2web"), rules=rules),
        hashlib.sha256(raw_bytes).hexdigest(),
    )


def _authorized_file(path: Path, root: Path) -> Path:
    """解析文件并拒绝逃逸用户本次授权目录的符号链接路径。"""
    resolved = Path(path).expanduser().resolve()
    root_resolved = Path(root).expanduser().resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("任务或安全清单必须位于用户授权目录内") from exc
    if not resolved.is_file():
        raise ValueError(f"找不到任务或安全清单文件：{resolved}")
    return resolved


def _task_from_raw(raw: Any) -> OnlineMind2WebTask:
    """兼容上游字段名并把一条 JSON 任务转为强类型记录。"""
    if not isinstance(raw, dict):
        raise ValueError("任务项必须是对象")
    return OnlineMind2WebTask(
        task_id=str(raw.get("task_id") or "").strip(),
        website=str(raw.get("website") or "").strip(),
        instruction=str(
            raw.get("task_description") or raw.get("confirmed_task") or raw.get("instruction") or ""
        ).strip(),
        reference_length=_positive_int(raw.get("reference_length"), "reference_length"),
    )


def _rule_from_raw(raw: Any) -> SafetyRule:
    """把安全清单单项转为不可变规则并拒绝自由格式值。"""
    if not isinstance(raw, dict):
        raise ValueError("安全规则必须是对象")
    domains = raw.get("allowed_domains")
    values = raw.get("allowed_type_values", [])
    if not isinstance(domains, list) or not all(isinstance(item, str) and item for item in domains):
        raise ValueError("allowed_domains 必须是非空字符串数组")
    if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
        raise ValueError("allowed_type_values 必须是字符串数组")
    return SafetyRule(
        task_id=str(raw.get("task_id") or "").strip(),
        allowed_domains=tuple(item.lower() for item in domains),
        max_steps=_positive_int(raw.get("max_steps"), "max_steps"),
        timeout_seconds=_positive_int(raw.get("timeout_seconds"), "timeout_seconds"),
        allowed_type_values=tuple(values),
    )


def _positive_int(value: Any, name: str) -> int:
    """把配置收成正整数，布尔值和非数字一律拒绝。"""
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是正整数")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 必须是正整数") from exc
    if result <= 0:
        raise ValueError(f"{name} 必须是正整数")
    return result
