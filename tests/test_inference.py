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


def test_load_settings_default_max_iterations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """未设置环境变量时迭代上限为 20。"""
    monkeypatch.delenv("MAX_GUI_MAX_ITERATIONS", raising=False)
    monkeypatch.setenv("MAX_GUI_ROOT", str(tmp_path))
    settings = load_settings(workspace=tmp_path)
    assert settings.max_iterations == 20


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
    if isinstance(content, list):
        assert all(part.get("type") != "image_url" for part in content)
    else:
        assert content == "hello"


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


def test_inject_system_unless_already_present(settings: Settings) -> None:
    """调用方提供 system 时插到最前；原始已有则不重复。"""
    with_system = to_chat_messages(
        [{"role": "user", "content": {"text": "hi", "images": []}}],
        settings=settings,
        system="先截图",
    )
    assert with_system[0] == {"role": "system", "content": "先截图"}
    assert with_system[1]["role"] == "user"
    already = to_chat_messages(
        [{"role": "system", "content": "已有"}, {"role": "user", "content": "hi"}],
        settings=settings,
        system="先截图",
    )
    assert [item["role"] for item in already if item["role"] == "system"] == ["system"]
    assert already[0]["content"] == "已有"


def test_only_last_two_images_get_image_url(tmp_path: Path, settings: Settings) -> None:
    """第三张更早的截图只留路径摘要。"""
    paths = []
    for index in range(3):
        path = tmp_path / f"shot{index}.png"
        Image.new("RGB", (16, 16), color=(index * 40, 20, 20)).save(path)
        paths.append(path)
    encoded = to_chat_messages(
        [
            {
                "role": "tool",
                "tool_call_id": f"c{index}",
                "content": {
                    "text": json.dumps(
                        {"path": str(path), "view_width": 10 + index, "view_height": 8}
                    ),
                    "images": [{"path": str(path)}],
                },
            }
            for index, path in enumerate(paths)
        ],
        settings=settings,
    )

    def image_parts(message: dict) -> int:
        content = message["content"]
        if not isinstance(content, list):
            return 0
        return sum(1 for part in content if part.get("type") == "image_url")

    assert image_parts(encoded[0]) == 0
    assert "历史截图已省略" in encoded[0]["content"]
    assert str(paths[0]) in encoded[0]["content"]
    assert image_parts(encoded[1]) == 1
    assert image_parts(encoded[2]) == 1


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
    assert result.reasoning == ""
    assert tokens == ["你", "好"]


def _sse_mixed() -> str:
    """思考走 `reasoning_content`，正文走 `content`。"""
    chunks = [
        {"choices": [{"delta": {"reasoning_content": "先看"}, "finish_reason": None}]},
        {"choices": [{"delta": {"reasoning": "图"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "好"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]
    lines = [f"data: {json.dumps(item)}" for item in chunks]
    lines.append("data: [DONE]")
    return "\n".join(lines) + "\n"


async def test_stream_reasoning_separate_from_content(settings: Settings) -> None:
    """思考回调与正文回调分开，思考不进入 `text`。"""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_mixed().encode(),
        )

    client = InferenceClient(settings, transport=httpx.MockTransport(handler), check_weights=False)
    tokens: list[str] = []
    thoughts: list[str] = []
    result = await client.stream(
        [{"role": "user", "content": "hi"}],
        on_token=tokens.append,
        on_reasoning=thoughts.append,
    )
    assert result.reasoning == "先看图"
    assert result.text == "好"
    assert thoughts == ["先看", "图"]
    assert tokens == ["好"]
    assert "先看" not in "".join(tokens)


def test_assistant_reasoning_not_encoded(settings: Settings) -> None:
    """编码发给模型时丢掉助手 `reasoning`，只保留正文。"""
    messages = to_chat_messages(
        [
            {
                "role": "assistant",
                "content": {"text": "已完成", "reasoning": "先截图再点微信"},
            }
        ],
        settings=settings,
    )
    assert messages[0]["content"] == "已完成"
    encoded = json.dumps(messages, ensure_ascii=False)
    assert "先截图再点微信" not in encoded


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
