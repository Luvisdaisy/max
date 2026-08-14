from __future__ import annotations

import json
from pathlib import Path

import httpx
from PIL import Image

from max_gui.config import Settings, UnknownModelError, resolve_model_alias
from max_gui.inference.client import (
    ConnectionFailedError,
    InferenceClient,
    encode_user_content,
    to_chat_messages,
)
from max_gui.inference.images import ImagePrepError, prepare_image


def test_unknown_alias_rejected() -> None:
    try:
        resolve_model_alias("not-a-model")
    except UnknownModelError:
        return
    raise AssertionError("expected UnknownModelError")


def test_default_alias_is_2b() -> None:
    assert resolve_model_alias("qwen2b") == "qwen3.5-2b"


def test_prepare_oversized_image(tmp_path: Path, settings: Settings) -> None:
    path = tmp_path / "big.png"
    Image.new("RGB", (200, 80), color="red").save(path)
    part = prepare_image(path, max_edge=settings.max_image_edge, max_bytes=settings.max_image_bytes)
    assert part["type"] == "image_url"
    assert part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_reject_non_image(tmp_path: Path, settings: Settings) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("hi", encoding="utf-8")
    try:
        prepare_image(path, max_edge=64, max_bytes=1000)
    except ImagePrepError:
        return
    raise AssertionError("expected ImagePrepError")


def test_text_only_payload_has_no_image(settings: Settings) -> None:
    parts = encode_user_content("hello", [], settings=settings)
    assert parts == [{"type": "text", "text": "hello"}]
    messages = to_chat_messages(
        [{"role": "user", "content": {"text": "hello", "images": []}}],
        settings=settings,
    )
    content = messages[0]["content"]
    assert all(part.get("type") != "image_url" for part in content)


def test_tool_result_text_only(settings: Settings) -> None:
    messages = to_chat_messages(
        [{"role": "tool", "tool_call_id": "c1", "content": "file body"}],
        settings=settings,
    )
    assert messages[0]["content"] == "file body"
    assert messages[0]["tool_call_id"] == "c1"
    assert isinstance(messages[0]["content"], str)


def test_tool_result_with_image(tmp_path: Path, settings: Settings) -> None:
    path = tmp_path / "shot.png"
    Image.new("RGB", (16, 16), color="green").save(path)
    messages = to_chat_messages(
        [
            {
                "role": "tool",
                "tool_call_id": "c2",
                "content": {"text": "截图完成", "images": [{"path": str(path)}]},
            }
        ],
        settings=settings,
    )
    types = [part["type"] for part in messages[0]["content"]]
    assert "text" in types and "image_url" in types


def test_tool_result_missing_image_keeps_text(settings: Settings, tmp_path: Path) -> None:
    missing = tmp_path / "gone.png"
    messages = to_chat_messages(
        [
            {
                "role": "tool",
                "content": {"text": "路径丢失", "images": [{"path": str(missing)}]},
            }
        ],
        settings=settings,
    )
    assert messages[0]["content"] == "路径丢失"


def test_text_plus_image_payload(tmp_path: Path, settings: Settings) -> None:
    path = tmp_path / "shot.png"
    Image.new("RGB", (16, 16), color="blue").save(path)
    messages = to_chat_messages(
        [{"role": "user", "content": {"text": "看", "images": [{"path": str(path)}]}}],
        settings=settings,
    )
    types = [part["type"] for part in messages[0]["content"]]
    assert "text" in types and "image_url" in types


def _sse(chunks: list[str]) -> str:
    lines = []
    for chunk in chunks:
        payload = {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
        lines.append(f"data: {json.dumps(payload)}")
    lines.append("data: [DONE]")
    return "\n".join(lines) + "\n"


async def test_stream_tokens(settings: Settings) -> None:
    body = _sse(["你", "好"])

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3.5-2b"
        assert payload["stream"] is True
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=body.encode()
        )

    client = InferenceClient(settings, transport=httpx.MockTransport(handler), check_weights=False)
    tokens: list[str] = []
    result = await client.stream([{"role": "user", "content": "hi"}], on_token=tokens.append)
    assert result.text == "你好"
    assert tokens == ["你", "好"]


async def test_connection_error_mentions_serve(settings: Settings) -> None:
    client = InferenceClient(settings, check_weights=False)
    try:
        await client.stream([{"role": "user", "content": "hi"}])
    except ConnectionFailedError as exc:
        assert "max-gui serve" in str(exc)
        return
    raise AssertionError("expected ConnectionFailedError")
