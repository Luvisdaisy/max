"""推理层：别名解析、图像预处理、多模态编码与流式客户端。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from max_gui.config import Settings, UnknownModelError, load_settings, resolve_model_alias
from max_gui.inference.client import (
    ConnectionFailedError,
    InferenceClient,
    encode_user_content,
    to_chat_messages,
)
from max_gui.inference.images import ImagePrepError, prepare_image


def test_unknown_alias_rejected() -> None:
    """未知别名抛 `UnknownModelError`。"""
    try:
        resolve_model_alias("not-a-model")
    except UnknownModelError:
        return
    raise AssertionError("expected UnknownModelError")


def test_default_alias_is_2b() -> None:
    """`qwen2b` 规范为 `qwen3.5-2b`。"""
    assert resolve_model_alias("qwen2b") == "qwen3.5-2b"


def test_load_settings_defaults_to_4b(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """未覆盖模型时默认别名是 `qwen3.5-4b`。"""
    monkeypatch.delenv("MAX_GUI_MODEL", raising=False)
    monkeypatch.setenv("MAX_GUI_ROOT", str(tmp_path))
    settings = load_settings(workspace=tmp_path)
    assert settings.canonical_model == "qwen3.5-4b"


def test_prepare_oversized_image(tmp_path: Path, settings: Settings) -> None:
    """超大图被压成 JPEG data URL。"""
    path = tmp_path / "big.png"
    Image.new("RGB", (200, 80), color="red").save(path)
    prepared = prepare_image(
        path, max_edge=settings.max_image_edge, max_bytes=settings.max_image_bytes
    )
    assert prepared.part["type"] == "image_url"
    assert prepared.part["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert prepared.width <= settings.max_image_edge
    assert prepared.height <= settings.max_image_edge


def test_prepare_reports_fitted_size(tmp_path: Path) -> None:
    """超长边缩放后返回的宽高等于实际发送尺寸。"""
    path = tmp_path / "wide.png"
    Image.new("RGB", (3000, 1000), color="red").save(path)
    prepared = prepare_image(path, max_edge=1500, max_bytes=2_000_000)
    assert prepared.width == 1500
    assert prepared.height == 500


def test_reject_non_image(tmp_path: Path, settings: Settings) -> None:
    """非图像文件被 `ImagePrepError` 拒绝。"""
    path = tmp_path / "notes.txt"
    path.write_text("hi", encoding="utf-8")
    try:
        prepare_image(path, max_edge=64, max_bytes=1000)
    except ImagePrepError:
        return
    raise AssertionError("expected ImagePrepError")


def test_text_only_payload_has_no_image(settings: Settings) -> None:
    """纯文本用户消息不含 `image_url`。"""
    parts = encode_user_content("hello", [], settings=settings)
    assert parts == [{"type": "text", "text": "hello"}]
    messages = to_chat_messages(
        [{"role": "user", "content": {"text": "hello", "images": []}}],
        settings=settings,
    )
    content = messages[0]["content"]
    assert all(part.get("type") != "image_url" for part in content)


def test_tool_result_text_only(settings: Settings) -> None:
    """纯文本工具结果保持字符串并带上 `tool_call_id`。"""
    messages = to_chat_messages(
        [{"role": "tool", "tool_call_id": "c1", "content": "file body"}],
        settings=settings,
    )
    assert messages[0]["content"] == "file body"
    assert messages[0]["tool_call_id"] == "c1"
    assert isinstance(messages[0]["content"], str)


def test_tool_result_with_image(tmp_path: Path, settings: Settings) -> None:
    """带图的工具结果编成 text + image_url。"""
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
    """图像丢失时工具结果退化为纯文本。"""
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
    """用户文本加图同时出现在 content 里。"""
    path = tmp_path / "shot.png"
    Image.new("RGB", (16, 16), color="blue").save(path)
    messages = to_chat_messages(
        [{"role": "user", "content": {"text": "看", "images": [{"path": str(path)}]}}],
        settings=settings,
    )
    types = [part["type"] for part in messages[0]["content"]]
    assert "text" in types and "image_url" in types


def _sse(chunks: list[str]) -> str:
    """把文本块编成 chat completions SSE 正文。"""
    lines = []
    for chunk in chunks:
        payload = {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
        lines.append(f"data: {json.dumps(payload)}")
    lines.append("data: [DONE]")
    return "\n".join(lines) + "\n"


async def test_stream_tokens(settings: Settings) -> None:
    """Mock 传输下逐 token 回调并拼出完整文本。"""
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


async def test_stream_http_error_includes_status(settings: Settings) -> None:
    """流式非 2xx 读出正文，错误含状态码且不含 httpx 内部文案。"""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "payload too large"})

    client = InferenceClient(settings, transport=httpx.MockTransport(handler), check_weights=False)
    try:
        await client.stream([{"role": "user", "content": "hi"}])
    except RuntimeError as exc:
        message = str(exc)
        assert "400" in message
        assert "without having called read" not in message
        assert "payload too large" in message
        return
    raise AssertionError("expected RuntimeError")


async def test_connection_error_mentions_serve(settings: Settings) -> None:
    """连不上服务时提示 `max-gui serve`。"""
    client = InferenceClient(settings, check_weights=False)
    try:
        await client.stream([{"role": "user", "content": "hi"}])
    except ConnectionFailedError as exc:
        assert "max-gui serve" in str(exc)
        return
    raise AssertionError("expected ConnectionFailedError")
