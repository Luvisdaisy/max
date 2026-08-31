"""主推理重试分类、退避与安全通知值对象。

对外入口为 `RetryNotice`、`RetryMetadata`、`RetryDecision`、
`classify_http_failure`、`classify_transport_failure` 与 `retry_delay_seconds`。
本模块只判断错误和计算等待，不发送请求，也不记录请求正文、图片或认证信息。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
NON_RETRYABLE_HTTP_STATUSES = frozenset({401, 403, 404, 405, 409, 413, 415, 422})
MAX_RETRY_DELAY_SECONDS = 40.0
_TRANSIENT_400_MARKERS = (
    "model_loading",
    "model loading",
    "server_busy",
    "server busy",
    "temporarily_unavailable",
    "temporarily unavailable",
    "upstream_unavailable",
    "upstream unavailable",
    "upstream_timeout",
    "upstream timeout",
    "service unavailable",
    "服务繁忙",
    "暂时不可用",
    "上游不可达",
    "上游超时",
)
_PERMANENT_400_MARKERS = (
    "model_not_found",
    "model not found",
    "authentication",
    "unauthorized",
    "context_length",
    "context length",
    "context window",
    "maximum context",
    "invalid_request",
    "invalid request",
    "invalid_tool",
    "invalid tool",
    "tool schema",
    "schema validation",
    "invalid schema",
    "invalid image",
    "invalid message",
    "unknown field",
    "missing field",
    "模型不存在",
    "鉴权失败",
    "上下文",
    "工具 schema",
    "参数非法",
    "字段非法",
)
_GENERIC_400_MARKERS = (
    "client error '400 bad request'",
    'client error "400 bad request"',
    "400 bad request for url",
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*[\"']?bearer\s+)[^\s,;\"'}]+"),
    re.compile(r"(?i)([\"']?(?:api[_-]?key|token)[\"']?\s*[:=]\s*[\"']?)[^\s,;\"'}]+"),
)


@dataclass(frozen=True, slots=True)
class RetryMetadata:
    """一次逻辑模型调用的网络尝试统计。

    字段：
        attempt_count: 已实际发起的网络请求次数。
        retry_count: 首次请求之外已实际发起的重试次数。
        reason_code: 最后一次失败的稳定内部原因码；成功时为空。
        status_code: 最后一次 HTTP 状态码；网络错误或成功时为空。
    """

    attempt_count: int = 1
    retry_count: int = 0
    reason_code: str | None = None
    status_code: int | None = None


@dataclass(frozen=True, slots=True)
class RetryNotice:
    """即将重新发送主推理请求的安全通知。

    字段：
        attempt: 下一次网络尝试的序号，从 2 开始。
        max_attempts: 当前配置允许的总尝试数。
        reason_code: 稳定内部原因码。
        status_code: 可选 HTTP 状态码。
        delay_ms: 发起下一次尝试前的等待毫秒。
        error: 截断后的安全错误摘要，不含请求载荷和认证信息。
    """

    attempt: int
    max_attempts: int
    reason_code: str
    status_code: int | None
    delay_ms: int
    error: str


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """一次失败的重试分类结果。

    字段：
        retryable: 是否允许在未输出流式增量时重放。
        reason_code: 稳定内部原因码。
        status_code: 可选 HTTP 状态码。
        detail: 最多 400 字符的安全摘要。
    """

    retryable: bool
    reason_code: str
    status_code: int | None
    detail: str


def classify_http_failure(status_code: int, detail: str, *, opaque: bool) -> RetryDecision:
    """按状态码与安全正文摘要判断 HTTP 失败是否可恢复。

    参数：
        status_code: HTTP 响应状态码。
        detail: 已截断且不含认证信息的响应摘要。
        opaque: 响应正文为空、不可读或只有通用客户端错误时为真。

    返回：
        可直接用于重试循环的分类结果。
    """
    detail = safe_retry_detail(detail)
    normalized = _normalized_error_text(detail)
    if status_code in RETRYABLE_HTTP_STATUSES:
        return RetryDecision(True, f"http_{status_code}", status_code, detail[:400])
    if status_code == 400:
        if opaque:
            return RetryDecision(True, "http_400_opaque", status_code, detail[:400])
        if any(marker in normalized for marker in _GENERIC_400_MARKERS):
            return RetryDecision(True, "http_400_opaque", status_code, detail[:400])
        if any(marker in normalized for marker in _PERMANENT_400_MARKERS):
            return RetryDecision(False, "http_400_invalid_request", status_code, detail[:400])
        if any(marker in normalized for marker in _TRANSIENT_400_MARKERS):
            return RetryDecision(True, "http_400_transient", status_code, detail[:400])
        return RetryDecision(False, "http_400_unknown", status_code, detail[:400])
    if status_code in NON_RETRYABLE_HTTP_STATUSES:
        return RetryDecision(False, f"http_{status_code}_permanent", status_code, detail[:400])
    return RetryDecision(False, f"http_{status_code}", status_code, detail[:400])


def classify_transport_failure(error: httpx.HTTPError) -> RetryDecision:
    """判断 `httpx` 网络异常是否属于可恢复传输故障。

    参数：
        error: HTTP 客户端抛出的网络异常。

    返回：
        不包含 URL、请求正文和认证头的分类结果。
    """
    retryable_types = (
        httpx.ConnectError,
        httpx.TimeoutException,
        httpx.ReadError,
        httpx.WriteError,
        httpx.RemoteProtocolError,
    )
    name = type(error).__name__
    return RetryDecision(
        isinstance(error, retryable_types),
        f"transport_{name.lower()}",
        None,
        name,
    )


def retry_delay_seconds(
    retry_number: int,
    *,
    random_value: float,
    retry_after: str | None = None,
    now: datetime | None = None,
) -> float:
    """计算第 `retry_number` 次重试前的有界等待。

    参数：
        retry_number: 从 1 开始的重试序号。
        random_value: 0–1 随机值，用于增加最多 20% 抖动。
        retry_after: 可选 HTTP `Retry-After` 秒数或日期。
        now: 解析 HTTP 日期时使用的当前 UTC 时间，测试可注入。

    返回：
        0–40 秒之间的等待时间。
    """
    server_delay = _parse_retry_after(retry_after, now=now)
    if server_delay is not None:
        return min(MAX_RETRY_DELAY_SECONDS, max(0.0, server_delay))
    base = min(32.0, 2.0 * (2 ** max(0, retry_number - 1)))
    jitter = base * 0.2 * min(1.0, max(0.0, random_value))
    return min(MAX_RETRY_DELAY_SECONDS, base + jitter)


def safe_retry_detail(value: object) -> str:
    """截断并遮蔽错误摘要中的常见认证信息。

    参数：
        value: HTTP 正文、异常类型或其它诊断值。

    返回：
        最多 400 字符且不含常见 Bearer、API Key 或 token 值的文本。
    """
    text = str(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1***", text)
    return text[:400]


def _normalized_error_text(detail: str) -> str:
    """把 JSON 或普通错误正文规范化为适合匹配的小写文本。"""
    try:
        payload = json.loads(detail)
    except (json.JSONDecodeError, TypeError):
        return detail.lower()
    return json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()


def _parse_retry_after(value: str | None, *, now: datetime | None) -> float | None:
    """解析 `Retry-After` 秒数或 HTTP 日期；非法值返回空。"""
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    current = now or datetime.now(UTC)
    return (target - current).total_seconds()
