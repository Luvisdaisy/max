"""OpenAI 兼容流式客户端：组装多模态消息并解析 SSE。

编码时最多回注最近一张仍存在的本地图；更早截图改成路径摘要。
可选把 GUI `system` 插到请求最前。
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from max_gui.config import Settings, require_provider_key, require_weights
from max_gui.inference.images import prepare_image


class ConnectionFailedError(RuntimeError):
    """连不上 `base_url`。本地提示 `serve`，云端提示检查网络与密钥。"""

    def __init__(self, base_url: str, *, hint: str | None = None) -> None:
        """参数：`base_url` 为尝试连接的端点；`hint` 覆盖默认文案。"""
        self.base_url = base_url
        super().__init__(hint or f"无法连接推理服务（{base_url}）。请先运行：max-gui serve")


@dataclass(slots=True)
class ChatDelta:
    """一次流式增量或拼好的完整回复。

    字段：
        text: 正文增量或累计正文。
        reasoning: 思考增量或累计思考；不并入 `text`。
        tool_calls: OpenAI 风格工具调用（流式时按 index 拼装）。
        finish_reason: `stop` / `interrupted` 等。
    """

    text: str = ""
    reasoning: str = ""
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
        on_reasoning: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> ChatDelta:
        """流式补全并拼成一条 `ChatDelta`。

        参数：
            messages: 已编码的 chat 消息。
            tools: 可选 function schema。
            on_token: 每段正文增量回调。
            on_reasoning: 每段思考增量回调；不触发 `on_token`。
            should_stop: 返回真则中止并标 `interrupted`。

        异常：
            ConnectionFailedError: 网络层失败。
            RuntimeError: HTTP 非 2xx。
        """
        if self.settings.provider == "modelscope":
            require_provider_key(self.settings)
        elif self.check_weights:
            require_weights(self.settings)

        payload: dict[str, Any] = {
            "model": self.settings.model_name,
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
                        if delta.reasoning:
                            assembled.reasoning += delta.reasoning
                            if on_reasoning:
                                on_reasoning(delta.reasoning)
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
            if self.settings.provider == "modelscope":
                raise ConnectionFailedError(
                    self.settings.base_url,
                    hint=(
                        f"无法连接推理服务（{self.settings.base_url}）。"
                        "请检查网络与 MAX_PROVIDER_KEY。"
                    ),
                ) from exc
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


MAX_INLINE_IMAGES = 1


def _collect_image_paths(content: dict[str, Any]) -> list[Path]:
    """从 `{images: [{path}]}` 取出仍存在的本地路径。"""
    images: list[Path] = []
    for ref in content.get("images") or []:
        path = Path(str(ref.get("path"))) if isinstance(ref, dict) else Path(str(ref))
        if path.is_file():
            images.append(path)
    return images


def _recent_image_slots(
    raw_messages: list[dict[str, Any]], *, limit: int = MAX_INLINE_IMAGES
) -> set[tuple[int, str]]:
    """按出现顺序取最后 `limit` 张仍存在的图，返回 `(消息下标, 路径)`。"""
    slots: list[tuple[int, str]] = []
    for index, message in enumerate(raw_messages):
        content = message.get("content")
        if not isinstance(content, dict):
            continue
        for path in _collect_image_paths(content):
            slots.append((index, str(path)))
    return set(slots[-limit:])


def _omit_note(path: Path, text: str) -> str:
    """历史图不编进请求时的路径与尺寸摘要。"""
    view: str | None = None
    try:
        payload = json.loads(text)
        if isinstance(payload, dict) and payload.get("view_width") and payload.get("view_height"):
            view = f"{payload['view_width']}×{payload['view_height']}"
    except json.JSONDecodeError:
        pass
    if view is None:
        try:
            with Image.open(path) as image:
                view = f"{image.width}×{image.height}"
        except Exception:
            view = None
    if view:
        return f"历史截图已省略：{path}，视图 {view}"
    return f"历史截图已省略：{path}"


def _encode_content(
    content: Any,
    *,
    settings: Settings,
    allowed_images: set[str] | None = None,
) -> Any:
    """编码单条 content：限额内的图编成 `image_url`，更早的改成文本摘要。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return content
    if isinstance(content, dict):
        images = _collect_image_paths(content)
        text = str(content.get("text") or "")
        keep = [path for path in images if allowed_images is None or str(path) in allowed_images]
        omitted = [path for path in images if path not in keep]
        if omitted:
            notes = "\n".join(_omit_note(path, text) for path in omitted)
            text = f"{text}\n{notes}" if text else notes
        if keep:
            return encode_user_content(text, keep, settings=settings)
        return text
    return str(content or "")


def to_chat_messages(
    raw_messages: list[dict[str, Any]],
    *,
    settings: Settings,
    system: str | None = None,
) -> list[dict[str, Any]]:
    """把会话状态消息转成 OpenAI chat 请求体，并回注最近一张图像。

    参数：
        raw_messages: 图状态中的消息。
        settings: 图像预处理上限。
        system: 若给出且原始消息不以 system 开头，则插到请求最前。

    返回：
        Chat Completions 的 `messages` 数组。
    """
    keep = _recent_image_slots(raw_messages)
    encoded: list[dict[str, Any]] = []
    for index, message in enumerate(raw_messages):
        role = message.get("role") or "user"
        item: dict[str, Any] = {"role": role}
        content = message.get("content")
        allowed = {path for slot_index, path in keep if slot_index == index}
        if role == "system":
            if isinstance(content, str):
                item["content"] = content
            elif isinstance(content, dict):
                item["content"] = str(content.get("text") or "")
            else:
                item["content"] = str(content or "")
            encoded.append(item)
            continue
        if role == "tool":
            if isinstance(content, dict):
                item["content"] = _encode_content(
                    content, settings=settings, allowed_images=allowed
                )
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
                item["content"] = _encode_content(
                    content, settings=settings, allowed_images=allowed
                )
            elif isinstance(content, str):
                item["content"] = content
            elif isinstance(content, dict):
                # 思考只给 TUI 回放，不编进下一轮请求。
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
            item["content"] = _encode_content(content, settings=settings, allowed_images=allowed)
        else:
            item["content"] = str(content or "")
        encoded.append(item)
    if system and (not encoded or encoded[0].get("role") != "system"):
        encoded.insert(0, {"role": "system", "content": system})
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
    reasoning = delta.get("reasoning_content")
    if reasoning is None:
        reasoning = delta.get("reasoning")
    return ChatDelta(
        text=str(delta.get("content") or ""),
        reasoning=str(reasoning or ""),
        tool_calls=list(delta.get("tool_calls") or []),
        finish_reason=choice.get("finish_reason"),
    )


async def collect_stream(stream: AsyncIterator[ChatDelta]) -> ChatDelta:
    """把异步增量流折成一条累计 `ChatDelta`。"""
    assembled = ChatDelta()
    async for delta in stream:
        assembled.text += delta.text
        assembled.reasoning += delta.reasoning
        assembled.tool_calls.extend(delta.tool_calls)
        assembled.finish_reason = delta.finish_reason or assembled.finish_reason
    return assembled
