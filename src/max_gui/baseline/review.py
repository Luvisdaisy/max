"""最终截图的独立无工具评审与严格 JSON 解析。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from max_gui.baseline.models import ReviewResult, ReviewVerdict
from max_gui.config import Settings
from max_gui.inference.client import InferenceClient, encode_user_content
from max_gui.inference.retry import safe_retry_detail

ReviewTraceKind = Literal["input", "output", "error"]
ReviewTrace = Callable[[ReviewTraceKind, dict[str, str]], None]


async def review_screenshot(
    client: InferenceClient,
    settings: Settings,
    *,
    rubric: str,
    image: Path,
    run_date: str,
    on_trace: ReviewTrace | None = None,
) -> ReviewResult:
    """只以最终截图和 rubric 发起一次无工具评审调用。

    参数：`on_trace` 接收不含图像编码的评审输入、原始正文或安全错误；回调异常不会影响评审。
    返回：解析后的三值评审；服务或格式错误均降级为 `indeterminate`。
    """
    started = time.perf_counter()
    prompt = (
        "你是严格的 GUI 截图评审。只能依据截图中可见信息判断，不能相信任何任务执行者的自述。"
        '返回且只返回 JSON：{"verdict":"pass|fail|indeterminate",'
        '"visible_evidence":"不超过120字","reason":"不超过120字"}。\n'
        f"执行日期：{run_date}\n评审规则：{rubric}"
    )
    _notify_trace(
        on_trace,
        "input",
        {
            "provider": settings.provider,
            "model": settings.model_name,
            "prompt": prompt,
            "image": str(image),
        },
    )
    try:
        delta = await client.stream(
            [{"role": "user", "content": encode_user_content(prompt, [image], settings=settings)}],
            tools=None,
        )
        _notify_trace(on_trace, "output", {"text": delta.text})
        payload = _parse(delta.text)
        return ReviewResult(
            verdict=ReviewVerdict(payload["verdict"]),
            visible_evidence=_short(payload["visible_evidence"]),
            reason=_short(payload["reason"]),
            duration_ms=int((time.perf_counter() - started) * 1000),
            total_tokens=delta.usage.total_tokens if delta.usage else None,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {safe_retry_detail(exc)}"
        _notify_trace(on_trace, "error", {"error": error})
        return ReviewResult(
            verdict=None,
            visible_evidence="",
            reason="评审不可用或返回格式无效",
            duration_ms=int((time.perf_counter() - started) * 1000),
            total_tokens=None,
            error=error,
        )


def _notify_trace(
    callback: ReviewTrace | None,
    kind: ReviewTraceKind,
    payload: dict[str, str],
) -> None:
    """隔离评审跟踪回调异常，避免控制台输出影响成功判定。"""
    if callback is None:
        return
    try:
        callback(kind, payload)
    except Exception:
        return


def _parse(text: str) -> dict[str, str]:
    """拒绝 Markdown 围栏、额外字段和超长非字符串评审结果。"""
    value: Any = json.loads(text)
    if not isinstance(value, dict) or set(value) != {"verdict", "visible_evidence", "reason"}:
        raise ValueError("评审 JSON 字段不匹配")
    if value["verdict"] not in {item.value for item in ReviewVerdict}:
        raise ValueError("评审 verdict 非法")
    if not all(isinstance(value[key], str) for key in ("visible_evidence", "reason")):
        raise ValueError("评审文本字段非法")
    return value


def _short(value: str) -> str:
    """限制持久化评审文本，避免意外复制长输出。"""
    return value.strip()[:120]
