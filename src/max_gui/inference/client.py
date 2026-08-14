"""OpenAI 兼容流式客户端：组装多模态消息并解析 SSE。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from max_gui.config import Settings, require_weights
from max_gui.inference.images import prepare_image


class ConnectionFailedError(RuntimeError):
    """连不上 `base_url`，提示先 `max-gui serve`。"""

    def __init__(self, base_url: str) -> None:
        """参数：`base_url` 为尝试连接的推理端点。"""
        self.base_url = base_url
        super().__init__(f"无法连接推理服务（{base_url}）。请先运行：max-gui serve")


@dataclass(slots=True)
class ChatDelta:
    """一次流式增量或拼好的完整回复。

    字段：
        text: 文本增量或累计文本。
        tool_calls: OpenAI 风格工具调用（流式时按 index 拼装）。
        finish_reason: `stop` / `interrupted` 等。
    """

    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    finish_reason: str | None = None


class InferenceClient:
    """对 `/chat/completions` 发流式请求。"""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        check_weights: bool = True,
    ) -> None:
        """参数：`transport` 供测试注入；`check_weights` 为假时跳过本地权重检查。"""
        self.settings = settings
        self._transport = transport
        self.check_weights = check_weights

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        on_token: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> ChatDelta:
        """流式补全并拼成一条 `ChatDelta`。

        参数：
            messages: 已编码的 chat 消息。
            tools: 可选 function schema。
            on_token: 每段文本增量回调。
            should_stop: 返回真则中止并标 `interrupted`。

        异常：
            ConnectionFailedError: 网络层失败。
            RuntimeError: HTTP 非 2xx。
        """
        if self.check_weights:
            require_weights(self.settings)

        payload: dict[str, Any] = {
            "model": self.settings.canonical_model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        url = self.settings.base_url.rstrip("/") + "/chat/completions"
        assembled = ChatDelta()
        tool_acc: dict[int, dict[str, Any]] = {}

        try:
            async with httpx.AsyncClient(timeout=120.0, transport=self._transport) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if should_stop and should_stop():
                            assembled.finish_reason = "interrupted"
                            break
                        delta = _parse_sse_line(line)
                        if delta is None:
                            continue
                        if delta.text:
                            assembled.text += delta.text
                            if on_token:
                                on_token(delta.text)
                        for call in delta.tool_calls:
                            index = int(call.get("index") or 0)
                            slot = tool_acc.setdefault(
                                index,
                                {
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""},
                                },
                            )
                            if call.get("id"):
                                slot["id"] = call["id"]
                            fn = call.get("function") or {}
                            if fn.get("name"):
                                slot["function"]["name"] += fn["name"]
                            if fn.get("arguments"):
                                slot["function"]["arguments"] += fn["arguments"]
                        if delta.finish_reason:
                            assembled.finish_reason = delta.finish_reason
        except httpx.HTTPStatusError as exc:
            detail = await _http_error_detail(exc)
            raise RuntimeError(f"推理服务返回 {exc.response.status_code}：{detail}") from exc
        except httpx.HTTPError as exc:
            raise ConnectionFailedError(self.settings.base_url) from exc

        assembled.tool_calls = [tool_acc[key] for key in sorted(tool_acc)]
        return assembled


async def _http_error_detail(exc: httpx.HTTPStatusError) -> str:
    """读取流式响应正文；失败则退回异常字符串。"""
    try:
        raw = await exc.response.aread()
        text = raw.decode("utf-8", errors="replace").strip()
        if text:
            return text[:400]
    except Exception:
        pass
    return str(exc)[:400]


def encode_user_content(
    text: str,
    image_paths: list[Path],
    *,
    settings: Settings,
) -> list[dict[str, Any]]:
    """把用户文本与本地图像编成多模态 content 数组。"""
    parts: list[dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})
    for path in image_paths:
        parts.append(
            prepare_image(
                path,
                max_edge=settings.max_image_edge,
                max_bytes=settings.max_image_bytes,
            ).part
        )
    return parts or [{"type": "text", "text": ""}]


def _collect_image_paths(content: dict[str, Any]) -> list[Path]:
    """从 `{images: [{path}]}` 取出仍存在的本地路径。"""
    images: list[Path] = []
    for ref in content.get("images") or []:
        path = Path(str(ref.get("path"))) if isinstance(ref, dict) else Path(str(ref))
        if path.is_file():
            images.append(path)
    return images


def _encode_content(content: Any, *, settings: Settings) -> Any:
    """编码单条 content：有图则多模态，否则纯文本。缺失图像只保留文字。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return content
    if isinstance(content, dict):
        images = _collect_image_paths(content)
        text = str(content.get("text") or "")
        if images:
            return encode_user_content(text, images, settings=settings)
        return text
    return str(content or "")


def to_chat_messages(
    raw_messages: list[dict[str, Any]], *, settings: Settings
) -> list[dict[str, Any]]:
    """把会话状态消息转成 OpenAI chat 请求体，并回注工具结果中的图像。"""
    encoded: list[dict[str, Any]] = []
    for message in raw_messages:
        role = message.get("role") or "user"
        item: dict[str, Any] = {"role": role}
        content = message.get("content")
        if role == "tool":
            if isinstance(content, dict):
                item["content"] = _encode_content(content, settings=settings)
            elif isinstance(content, str):
                item["content"] = content
            else:
                item["content"] = json.dumps(content, ensure_ascii=False)
            if message.get("tool_call_id"):
                item["tool_call_id"] = message["tool_call_id"]
            encoded.append(item)
            continue
        if role == "assistant":
            if isinstance(content, dict) and content.get("images"):
                item["content"] = _encode_content(content, settings=settings)
            elif isinstance(content, str):
                item["content"] = content
            elif isinstance(content, dict):
                item["content"] = content.get("text") or ""
            else:
                item["content"] = content
            if message.get("tool_calls"):
                item["tool_calls"] = message["tool_calls"]
            encoded.append(item)
            continue

        if isinstance(content, str):
            item["content"] = content
        elif isinstance(content, list):
            item["content"] = content
        elif isinstance(content, dict):
            item["content"] = encode_user_content(
                str(content.get("text") or ""),
                _collect_image_paths(content),
                settings=settings,
            )
        else:
            item["content"] = str(content or "")
        encoded.append(item)
    return encoded


def _parse_sse_line(line: str) -> ChatDelta | None:
    """解析一行 `data: ...` SSE；非数据行或坏 JSON 返回 `None`。"""
    text = line.strip()
    if not text or not text.startswith("data:"):
        return None
    data = text[5:].strip()
    if data == "[DONE]":
        return ChatDelta(finish_reason="stop")
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = payload.get("choices") or []
    if not choices:
        return None
    choice = choices[0]
    delta = choice.get("delta") or {}
    return ChatDelta(
        text=str(delta.get("content") or ""),
        tool_calls=list(delta.get("tool_calls") or []),
        finish_reason=choice.get("finish_reason"),
    )


async def collect_stream(stream: AsyncIterator[ChatDelta]) -> ChatDelta:
    """把异步增量流折成一条累计 `ChatDelta`。"""
    assembled = ChatDelta()
    async for delta in stream:
        assembled.text += delta.text
        assembled.tool_calls.extend(delta.tool_calls)
        assembled.finish_reason = delta.finish_reason or assembled.finish_reason
    return assembled
