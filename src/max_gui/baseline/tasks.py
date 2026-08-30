"""加载并严格校验真实桌面基线任务定义。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from max_gui.baseline.models import BaselineTask, RiskLevel

DEFAULT_TASKS = (
    Path(__file__).resolve().parents[3] / "artifacts" / "benchmarks" / "baseline-desktop-v1.json"
)


def load_tasks(path: Path = DEFAULT_TASKS) -> tuple[tuple[BaselineTask, ...], str]:
    """读取恰好五条基线任务并返回内容摘要。

    异常：文件不存在、JSON 结构或任务字段无效时抛出 `ValueError`。
    """
    if not path.is_file():
        raise ValueError(f"未找到基线任务文件：{path}")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("基线任务文件不是合法 JSON") from exc
    if not isinstance(payload, dict) or payload.get("version") != "baseline-desktop-v1":
        raise ValueError("基线任务版本必须为 baseline-desktop-v1")
    items = payload.get("tasks")
    if not isinstance(items, list) or len(items) != 5:
        raise ValueError("基线任务文件必须恰好包含五条任务")
    tasks: list[BaselineTask] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("基线任务必须是对象")
        try:
            task = BaselineTask(
                id=_text(item, "id"),
                prompt=_text(item, "prompt"),
                review_rubric=_text(item, "review_rubric"),
                preconditions=_texts(item, "preconditions"),
                risk=RiskLevel(_text(item, "risk")),
                timeout_seconds=_positive(item, "timeout_seconds"),
                nonce_template=str(item["nonce_template"]) if item.get("nonce_template") else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"基线任务字段无效：{item.get('id', '<unknown>')}") from exc
        tasks.append(task)
    if len({task.id for task in tasks}) != len(tasks):
        raise ValueError("基线任务 ID 不可重复")
    if tuple(task.id for task in tasks) != (
        "weather",
        "terminal",
        "calculator",
        "reminders",
        "wechat",
    ):
        raise ValueError("基线任务 ID 与固定执行顺序不符")
    return tuple(tasks), hashlib.sha256(raw).hexdigest()


def _text(item: dict[str, object], key: str) -> str:
    """读取非空字符串字段。"""
    value = item[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(key)
    return value.strip()


def _texts(item: dict[str, object], key: str) -> tuple[str, ...]:
    """读取非空字符串数组字段。"""
    value = item[key]
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(part, str) and part for part in value)
    ):
        raise ValueError(key)
    return tuple(value)


def _positive(item: dict[str, object], key: str) -> int:
    """读取正整数限制字段。"""
    value = item[key]
    if not isinstance(value, int) or value <= 0:
        raise ValueError(key)
    return value
