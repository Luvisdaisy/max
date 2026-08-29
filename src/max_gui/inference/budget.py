"""主推理上下文预算：保守估算文本与 schema，并按完整工具链裁剪。

对外入口为 `select_context_chains`。本模块不加载 tokenizer，不读取消息正文以外的
外部资源；估算只用于发送前保护，真实 token 用量仍以 provider 返回的 usage 为准。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import ceil
from typing import Any

from max_gui.config import Settings


class ContextBudgetExceededError(RuntimeError):
    """system、用户消息、工具 schema 与图片预留已经超过可用输入预算。"""

    def __init__(self, *, estimated: int, available: int, context_window: int) -> None:
        """用纯计数构造中文错误，不复制 prompt 或工具内容。"""
        super().__init__(
            "主推理上下文预算不足："
            f"估算基础输入 {estimated} token，可用 {available} token，"
            f"上下文容量 {context_window} token。"
        )


@dataclass(frozen=True, slots=True)
class ContextSelection:
    """按预算选择后的消息与脱敏诊断。

    字段：
        messages: 当前用户消息加最近完整工具链。
        estimated_input_tokens: 最终请求的保守输入估算。
        available_input_tokens: 扣除输出、安全和图片预留后的输入上限。
        included_chain_count: 纳入请求的完整工具链数。
        excluded_chain_count: 因六链上限或预算被排除的工具链数。
    """

    messages: list[dict[str, Any]]
    estimated_input_tokens: int
    available_input_tokens: int
    included_chain_count: int
    excluded_chain_count: int


def estimate_tokens(value: Any) -> int:
    """以 UTF-8 每两字节一个 token 保守估算可 JSON 序列化值。

    参数：
        value: 消息、schema、字符串或其它 JSON 兼容对象。

    返回：
        至少为一的估算 token 数。

    异常：
        不抛出序列化异常；未知对象退化为字符串。
    """
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            text = str(value)
    return max(1, ceil(len(text.encode("utf-8")) / 2))


def select_context_chains(
    *,
    user_message: dict[str, Any],
    chains: list[list[dict[str, Any]]],
    system: str,
    tools: list[dict[str, Any]],
    has_inline_image: bool,
    settings: Settings,
    recent_chain_limit: int = 6,
) -> ContextSelection:
    """从最近向前装入完整工具链，绝不拆开 assistant 与 tool 结果。

    参数：
        user_message: 当前任务唯一的用户消息。
        chains: 按时间正序排列的完整工具调用链。
        system: 本轮系统契约。
        tools: 本轮动态工具 schema。
        has_inline_image: 是否会编码唯一内联图片。
        settings: 上下文容量与三项预留。
        recent_chain_limit: 候选历史链硬上限，默认六条。

    返回：
        选择后的消息和只含计数的诊断。

    异常：
        ContextBudgetExceededError: 基础请求已经没有可用输入空间。
    """
    image_reserve = settings.image_token_reserve if has_inline_image else 0
    available = (
        settings.context_window
        - settings.max_output_tokens
        - settings.context_safety_margin
        - image_reserve
    )
    base = estimate_tokens(system) + estimate_tokens(user_message) + estimate_tokens(tools)
    if available <= 0 or base > available:
        raise ContextBudgetExceededError(
            estimated=base,
            available=max(0, available),
            context_window=settings.context_window,
        )

    candidates = chains[-recent_chain_limit:]
    selected: list[list[dict[str, Any]]] = []
    estimated = base
    for chain in reversed(candidates):
        chain_tokens = estimate_tokens(chain)
        if estimated + chain_tokens > available:
            break
        selected.append(chain)
        estimated += chain_tokens

    messages = [user_message]
    for chain in reversed(selected):
        messages.extend(chain)
    return ContextSelection(
        messages=messages,
        estimated_input_tokens=estimated,
        available_input_tokens=available,
        included_chain_count=len(selected),
        excluded_chain_count=max(0, len(chains) - len(selected)),
    )
