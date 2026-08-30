"""推理层：别名解析、图像预处理、多模态编码与流式客户端。"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from max_gui.config import (
    ContextBudgetConfigError,
    InferenceRetryConfigError,
    Settings,
    load_settings,
)
from max_gui.inference.budget import ContextBudgetExceededError, select_context_chains
from max_gui.inference.client import (
    ConnectionFailedError,
    InferenceClient,
    InferenceRequestError,
    encode_user_content,
    to_chat_messages,
)
from max_gui.inference.images import ImagePrepError, prepare_image
from max_gui.inference.retry import retry_delay_seconds, safe_retry_detail
from max_gui.provider import (
    PROVIDERS,
    MissingProviderKeyError,
    UnknownProviderError,
    get_provider,
    has_provider_key,
    require_provider_key,
)


def _isolate_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """把配置根指到临时目录，避免读仓库 `.env`。"""
    monkeypatch.setenv("MAX_GUI_ROOT", str(tmp_path))
    (tmp_path / "model").mkdir(exist_ok=True)
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")


def test_load_settings_defaults_to_ollama(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """未覆盖 provider 时默认使用固定的 Ollama 配置。"""
    _isolate_root(monkeypatch, tmp_path)
    settings = load_settings(workspace=tmp_path)
    assert settings.provider == "ollama"
    assert settings.model_name == "qwen3-vl:30b"
    assert settings.inference_max_retries == 5


@pytest.mark.parametrize("value", [0, 5])
def test_load_settings_accepts_retry_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    value: int,
) -> None:
    """主推理重试次数允许关闭或取到上界。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_GUI_INFERENCE_MAX_RETRIES", str(value))
    assert load_settings(workspace=tmp_path).inference_max_retries == value


@pytest.mark.parametrize("value", ["-1", "6", "abc"])
def test_load_settings_rejects_invalid_retry_count(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    value: str,
) -> None:
    """越界或非整数的主推理重试配置在启动阶段失败。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_GUI_INFERENCE_MAX_RETRIES", value)
    with pytest.raises(InferenceRetryConfigError, match="0–5"):
        load_settings(workspace=tmp_path)


def test_ollama_context_window_is_256k_and_independent_from_ocr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ollama 固定使用 256K 主上下文，OCR 的长度变量不会覆盖它。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "ollama")
    monkeypatch.setenv("MAX_GUI_MAX_MODEL_LEN", "4096")
    settings = load_settings(workspace=tmp_path)
    assert settings.context_window == 262_144
    assert settings.max_model_len == 4096
    assert settings.max_output_tokens == 8192
    assert settings.context_safety_margin == 4096


def test_cloud_provider_uses_conservative_context_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """非 Ollama provider 使用注册表中的保守上下文容量。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "modelscope")
    monkeypatch.setenv("MAX_MODELSCOPE_KEY", "tok")
    settings = load_settings(workspace=tmp_path)
    assert settings.context_window == 32_768


def test_invalid_context_reserves_fail_during_settings_load(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """输出和安全预留耗尽 provider 容量时在启动阶段失败。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "modelscope")
    monkeypatch.setenv("MAX_GUI_MAX_OUTPUT_TOKENS", "30000")
    monkeypatch.setenv("MAX_GUI_CONTEXT_SAFETY_MARGIN", "4096")
    with pytest.raises(ContextBudgetConfigError):
        load_settings(workspace=tmp_path)


def test_context_budget_keeps_complete_recent_tool_chains(settings: Settings) -> None:
    """预算裁剪从最近链向前选择，绝不留下孤立 tool 消息。"""
    settings.context_window = 700
    settings.max_output_tokens = 100
    settings.context_safety_margin = 100
    settings.image_token_reserve = 0
    old_chain = [
        {
            "role": "assistant",
            "content": "旧链" * 500,
            "tool_calls": [{"id": "old", "function": {"name": "screen_info"}}],
        },
        {"role": "tool", "tool_call_id": "old", "content": "旧结果"},
    ]
    recent_chain = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "new", "function": {"name": "screen_info"}}],
        },
        {"role": "tool", "tool_call_id": "new", "content": "新结果"},
    ]
    selected = select_context_chains(
        user_message={"role": "user", "content": "当前任务"},
        chains=[old_chain, recent_chain],
        system="系统契约",
        tools=[],
        has_inline_image=False,
        settings=settings,
    )
    assert selected.messages[1:] == recent_chain
    assert selected.included_chain_count == 1
    assert selected.excluded_chain_count == 1


def test_context_budget_rejects_base_request_before_network(settings: Settings) -> None:
    """基础消息、schema 与图片预留已经超限时直接抛出预算错误。"""
    settings.context_window = 100
    settings.max_output_tokens = 40
    settings.context_safety_margin = 30
    settings.image_token_reserve = 50
    with pytest.raises(ContextBudgetExceededError):
        select_context_chains(
            user_message={"role": "user", "content": "任务"},
            chains=[],
            system="系统契约",
            tools=[],
            has_inline_image=True,
            settings=settings,
        )


def test_load_settings_default_max_iterations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """未设置环境变量时迭代上限为 20。"""
    monkeypatch.delenv("MAX_GUI_MAX_ITERATIONS", raising=False)
    _isolate_root(monkeypatch, tmp_path)
    settings = load_settings(workspace=tmp_path)
    assert settings.max_iterations == 20


def test_env_file_sets_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """根目录 `.env` 写入 `MAX_PROVIDER` 后生效。"""
    _isolate_root(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text(
        "MAX_PROVIDER=modelscope\nMAX_MODELSCOPE_KEY=tok-from-file\n",
        encoding="utf-8",
    )
    settings = load_settings(workspace=tmp_path)
    assert settings.provider == "modelscope"
    assert settings.model_name == "Qwen/Qwen3.8-27B"
    assert settings.api_key == "tok-from-file"
    assert settings.base_url == PROVIDERS["modelscope"].base_url


def test_process_env_overrides_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """进程里已有 `MAX_PROVIDER` 时不被 `.env` 覆盖。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "ollama")
    (tmp_path / ".env").write_text("MAX_PROVIDER=modelscope\n", encoding="utf-8")
    settings = load_settings(workspace=tmp_path)
    assert settings.provider == "ollama"
    assert settings.model_name == "qwen3-vl:30b"


@pytest.mark.parametrize("provider", ["local", "remote"])
def test_removed_provider_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, provider: str
) -> None:
    """已移除的 provider 在配置加载阶段以中文错误拒绝。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", provider)
    with pytest.raises(UnknownProviderError) as exc:
        load_settings(workspace=tmp_path)
    assert provider in str(exc.value)
    assert "ollama" in str(exc.value)
    assert "local" not in str(exc.value).split("可用：", maxsplit=1)[-1]
    assert "remote" not in str(exc.value).split("可用：", maxsplit=1)[-1]


async def test_ollama_uses_registered_config_without_auth_and_with_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ollama 不查本地权重，且复用无认证的 OpenAI 工具调用请求。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "ollama")
    settings = load_settings(workspace=tmp_path)
    settings.inference_max_retries = 0
    tools = [{"type": "function", "function": {"name": "screenshot", "parameters": {}}}]
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        payload = json.loads(request.content)
        seen["model"] = payload["model"]
        seen["tools"] = payload.get("tools")
        seen["tool_choice"] = payload.get("tool_choice")
        seen["max_tokens"] = payload.get("max_tokens")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(["ok"]).encode(),
        )

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    result = await client.stream([{"role": "user", "content": "hi"}], tools=tools)
    assert result.text == "ok"
    assert seen == {
        "url": "http://192.168.1.158:11434/v1/chat/completions",
        "authorization": None,
        "model": "qwen3-vl:30b",
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": 8192,
    }


async def test_ollama_connection_error_has_lan_hint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Ollama 连不上时提示 WSL、防火墙和局域网端口，不提示本机 serve。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "ollama")
    settings = load_settings(workspace=tmp_path)
    settings.inference_max_retries = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    try:
        await client.stream([{"role": "user", "content": "hi"}])
    except ConnectionFailedError as exc:
        message = str(exc)
        assert "WSL Ollama" in message
        assert "Windows 防火墙" in message
        assert "局域网端口" in message
        assert "max-gui serve" not in message
        return
    raise AssertionError("expected ConnectionFailedError")


def test_modelscope_default_model_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`modelscope` 使用注册表定义的 Qwen3.8-27B。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "modelscope")
    monkeypatch.setenv("MAX_MODELSCOPE_KEY", "tok")
    settings = load_settings(workspace=tmp_path)
    assert settings.model_name == "Qwen/Qwen3.8-27B"


def test_unknown_provider_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """非法 `MAX_PROVIDER` 抛 `UnknownProviderError`。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "openai")
    try:
        load_settings(workspace=tmp_path)
    except UnknownProviderError as exc:
        message = str(exc)
        assert "openai" in message
        assert "dashscope" in message
        return
    raise AssertionError("expected UnknownProviderError")


def test_dashscope_uses_registered_model_and_endpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`dashscope` 使用注册表中的固定模型与北京专属端点。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "dashscope")
    monkeypatch.setenv("MAX_DASHSCOPE_KEY", "sk-tok")
    settings = load_settings(workspace=tmp_path)
    assert settings.provider == "dashscope"
    assert settings.model_name == "qwen3.8-27b"
    assert settings.base_url == PROVIDERS["dashscope"].base_url
    assert settings.api_key == "sk-tok"


def test_dashscope_ignores_model_name_from_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`MODEL_NAME` 不再覆盖 `dashscope` 的代码内模型。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "dashscope")
    monkeypatch.setenv("MAX_DASHSCOPE_KEY", "sk-tok")
    monkeypatch.setenv("MODEL_NAME", "qwen3.5-plus")
    settings = load_settings(workspace=tmp_path)
    assert settings.model_name == "qwen3.8-27b"


def test_dashscope_missing_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`dashscope` 缺 `MAX_DASHSCOPE_KEY` 时视为缺密钥。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "dashscope")
    settings = load_settings(workspace=tmp_path)
    assert not has_provider_key(settings.api_key)
    try:
        require_provider_key(get_provider(settings.provider), settings.api_key)
    except MissingProviderKeyError as exc:
        assert "max-gui serve" not in str(exc)
        assert "dashscope" in str(exc)
        return
    raise AssertionError("expected MissingProviderKeyError")


def test_dashscope_env_not_used_as_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """仅有 `DASHSCOPE_API_KEY` 时仍视为缺密钥。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "dashscope")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-from-dashscope")
    settings = load_settings(workspace=tmp_path)
    assert not has_provider_key(settings.api_key)
    try:
        require_provider_key(get_provider(settings.provider), settings.api_key)
    except MissingProviderKeyError:
        return
    raise AssertionError("expected MissingProviderKeyError")


def test_sdk_token_not_used_as_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """仅有 `MODELSCOPE_SDK_TOKEN` 时仍视为缺密钥。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "modelscope")
    monkeypatch.setenv("MODELSCOPE_SDK_TOKEN", "sdk-token")
    settings = load_settings(workspace=tmp_path)
    assert not has_provider_key(settings.api_key)
    try:
        require_provider_key(get_provider(settings.provider), settings.api_key)
    except MissingProviderKeyError:
        return
    raise AssertionError("expected MissingProviderKeyError")


def test_old_shared_key_not_used(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """旧 `MAX_PROVIDER_KEY` 不会替代 OpenRouter 专属密钥。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "openrouter")
    monkeypatch.setenv("MAX_PROVIDER_KEY", "legacy-token")
    settings = load_settings(workspace=tmp_path)
    assert not has_provider_key(settings.api_key)
    with pytest.raises(MissingProviderKeyError, match="MAX_OPENROUTER_KEY"):
        require_provider_key(get_provider(settings.provider), settings.api_key)


def test_openrouter_uses_registered_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """OpenRouter 使用固定模型、端点与自己的密钥环境变量。"""
    _isolate_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MAX_PROVIDER", "openrouter")
    monkeypatch.setenv("MAX_OPENROUTER_KEY", "or-token")
    monkeypatch.setenv("MODEL_NAME", "ignored-model")
    settings = load_settings(workspace=tmp_path)
    assert settings.provider == "openrouter"
    assert settings.model_name == "qwen/qwen3.5-plus"
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.api_key == "or-token"


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


def test_only_last_image_gets_image_url(tmp_path: Path, settings: Settings) -> None:
    """更早的截图只留路径摘要，仅最后一张带 image_url。"""
    paths = []
    for index in range(2):
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


class _FailingStream(httpx.AsyncByteStream):
    """可在可选首段之后抛出读取错误的测试流。"""

    def __init__(self, first_chunk: bytes | None = None) -> None:
        """参数：`first_chunk` 为断流前可选发送的原始 SSE 字节。"""
        self.first_chunk = first_chunk

    async def __aiter__(self):
        """先发送首段，再模拟服务端提前断流。"""
        if self.first_chunk is not None:
            yield self.first_chunk
        raise httpx.ReadError("stream closed")


async def test_retry_recovers_from_transport_errors(settings: Settings) -> None:
    """两次连接失败后第三次成功，并保留一次逻辑调用的尝试统计。"""
    settings.inference_max_retries = 5
    attempts = 0
    waits: list[float] = []
    notices = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, content=_sse(["ok"]).encode())

    async def fake_sleep(delay: float) -> None:
        waits.append(delay)

    client = InferenceClient(
        settings,
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        random_value=lambda: 0.0,
    )
    result = await client.stream(
        [{"role": "user", "content": "hi"}],
        on_retry=notices.append,
    )
    assert result.text == "ok"
    assert result.attempt_count == 3
    assert result.retry_count == 2
    assert attempts == 3
    assert waits == [0.5, 1.0]
    assert [notice.attempt for notice in notices] == [2, 3]


@pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503, 504])
async def test_retryable_http_status_recovers(settings: Settings, status: int) -> None:
    """规范列出的瞬时 HTTP 状态在下一次请求恢复。"""
    settings.inference_max_retries = 1
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(status, text="temporary")
        return httpx.Response(200, content=_sse(["ok"]).encode())

    async def fake_sleep(_delay: float) -> None:
        return None

    client = InferenceClient(
        settings,
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        random_value=lambda: 0.0,
    )
    result = await client.stream([{"role": "user", "content": "hi"}])
    assert result.text == "ok"
    assert attempts == 2


async def test_retry_exhaustion_stops_after_six_attempts(settings: Settings) -> None:
    """默认五次重试耗尽后停止，并把次数写进连接错误。"""
    settings.inference_max_retries = 5
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("refused", request=request)

    async def fake_sleep(_delay: float) -> None:
        return None

    client = InferenceClient(
        settings,
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        random_value=lambda: 0.0,
    )
    with pytest.raises(ConnectionFailedError) as caught:
        await client.stream([{"role": "user", "content": "hi"}])
    assert attempts == 6
    assert caught.value.metadata.attempt_count == 6
    assert caught.value.metadata.retry_count == 5
    assert "已重试 5 次" in str(caught.value)


@pytest.mark.parametrize(
    ("body", "expected_reason"),
    [
        (b"", "http_400_opaque"),
        (b"Client error '400 Bad Request' for url", "http_400_opaque"),
        (b'{"code":"server_busy"}', "http_400_transient"),
    ],
)
async def test_retryable_http_400_recovers(
    settings: Settings,
    body: bytes,
    expected_reason: str,
) -> None:
    """无正文或明确瞬时原因的 HTTP 400 可重试。"""
    settings.inference_max_retries = 1
    attempts = 0
    notices = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(400, content=body)
        return httpx.Response(200, content=_sse(["ok"]).encode())

    async def fake_sleep(_delay: float) -> None:
        return None

    client = InferenceClient(
        settings,
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        random_value=lambda: 0.0,
    )
    result = await client.stream(
        [{"role": "user", "content": "hi"}],
        on_retry=notices.append,
    )
    assert result.text == "ok"
    assert notices[0].reason_code == expected_reason


@pytest.mark.parametrize(
    "body",
    [
        {"code": "model_not_found"},
        {"error": "maximum context length exceeded"},
        {"error": "invalid tool schema"},
    ],
)
async def test_permanent_http_400_is_not_retried(settings: Settings, body: dict) -> None:
    """模型、上下文和工具 schema 等永久 400 立即失败。"""
    settings.inference_max_retries = 5
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, json=body)

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(InferenceRequestError) as caught:
        await client.stream([{"role": "user", "content": "hi"}])
    assert attempts == 1
    assert caught.value.metadata.retry_count == 0


@pytest.mark.parametrize("status", [401, 403, 404, 413, 422])
async def test_permanent_http_status_is_not_retried(settings: Settings, status: int) -> None:
    """鉴权、模型、请求体和语义错误不进入重试。"""
    settings.inference_max_retries = 5
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status, text="permanent")

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(InferenceRequestError):
        await client.stream([{"role": "user", "content": "hi"}])
    assert attempts == 1


def test_retry_delay_uses_jitter_retry_after_and_cap() -> None:
    """退避采用指数基础、最多 20% 抖动，并限制服务端等待上限。"""
    assert retry_delay_seconds(1, random_value=0.0) == 0.5
    assert retry_delay_seconds(2, random_value=1.0) == 1.2
    assert retry_delay_seconds(5, random_value=0.0) == 8.0
    assert retry_delay_seconds(1, random_value=0.0, retry_after="3") == 3.0
    assert retry_delay_seconds(1, random_value=0.0, retry_after="90") == 30.0


def test_retry_detail_redacts_plain_and_json_credentials() -> None:
    """重试错误摘要会遮蔽普通文本和 JSON 中的认证值。"""
    detail = safe_retry_detail(
        'Authorization: Bearer secret-a, "api_key":"secret-b", "token":"secret-c"'
    )
    assert "secret-a" not in detail
    assert "secret-b" not in detail
    assert "secret-c" not in detail


async def test_retry_wait_can_be_interrupted(settings: Settings) -> None:
    """退避期间中断会阻止下一次网络请求。"""
    settings.inference_max_retries = 5
    attempts = 0
    stopped = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("refused", request=request)

    async def fake_sleep(_delay: float) -> None:
        nonlocal stopped
        stopped = True

    client = InferenceClient(
        settings,
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        random_value=lambda: 0.0,
    )
    result = await client.stream(
        [{"role": "user", "content": "hi"}],
        should_stop=lambda: stopped,
    )
    assert result.finish_reason == "interrupted"
    assert attempts == 1


async def test_disconnect_before_first_delta_is_retried(settings: Settings) -> None:
    """首个有效 SSE 增量前断流可以安全重放。"""
    settings.inference_max_retries = 1
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(200, stream=_FailingStream())
        return httpx.Response(200, content=_sse(["ok"]).encode())

    async def fake_sleep(_delay: float) -> None:
        return None

    client = InferenceClient(
        settings,
        transport=httpx.MockTransport(handler),
        sleep=fake_sleep,
        random_value=lambda: 0.0,
    )
    result = await client.stream([{"role": "user", "content": "hi"}])
    assert result.text == "ok"
    assert result.attempt_count == 2


@pytest.mark.parametrize(
    "chunk",
    [
        b'data: {"choices":[{"delta":{"content":"partial"},"finish_reason":null}]}\n\n',
        b'data: {"choices":[{"delta":{"reasoning":"thinking"},"finish_reason":null}]}\n\n',
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-1",'
        b'"function":{"name":"screenshot","arguments":""}}]},"finish_reason":null}]}\n\n',
    ],
)
async def test_disconnect_after_effective_delta_is_not_retried(
    settings: Settings,
    chunk: bytes,
) -> None:
    """正文、思考或工具分片输出后断流不会重放请求。"""
    settings.inference_max_retries = 5
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, stream=_FailingStream(chunk))

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    with pytest.raises(InferenceRequestError, match="已产生输出后中断"):
        await client.stream([{"role": "user", "content": "hi"}])
    assert attempts == 1


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

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    tokens: list[str] = []
    result = await client.stream([{"role": "user", "content": "hi"}], on_token=tokens.append)
    assert result.text == "你好"
    assert result.reasoning == ""
    assert tokens == ["你", "好"]
    assert result.usage is None


def _sse_with_usage(chunks: list[str], usage: dict) -> str:
    """正文块之后追加空 choices 的用量块。"""
    lines = []
    for chunk in chunks:
        payload = {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
        lines.append(f"data: {json.dumps(payload)}")
    lines.append(f"data: {json.dumps({'choices': [], 'usage': usage})}")
    lines.append("data: [DONE]")
    return "\n".join(lines) + "\n"


async def test_stream_requests_include_usage_and_parses_empty_choices(
    settings: Settings,
) -> None:
    """请求带 include_usage；空 choices 用量块被采纳且不触发正文回调。"""
    body = _sse_with_usage(
        ["你", "好"],
        {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20},
    )
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=body.encode()
        )

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    tokens: list[str] = []
    result = await client.stream([{"role": "user", "content": "hi"}], on_token=tokens.append)
    assert captured["stream"] is True
    assert captured["stream_options"] == {"include_usage": True}
    assert tokens == ["你", "好"]
    assert result.text == "你好"
    assert result.usage is not None
    assert result.usage.prompt_tokens == 12
    assert result.usage.completion_tokens == 8
    assert result.usage.total_tokens == 20


async def test_stream_usage_total_falls_back_to_sum(settings: Settings) -> None:
    """缺 total_tokens 时用输入加输出。"""
    body = _sse_with_usage(["ok"], {"prompt_tokens": 3, "completion_tokens": 4})

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=body.encode()
        )

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    result = await client.stream([{"role": "user", "content": "hi"}])
    assert result.usage is not None
    assert result.usage.total_tokens == 7


async def test_stream_without_usage_stays_unknown(settings: Settings) -> None:
    """整段流没有 usage 时用量为未知，不得写成 0。"""
    body = _sse(["只", "有", "正文"])

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=body.encode()
        )

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    result = await client.stream([{"role": "user", "content": "hi"}])
    assert result.text == "只有正文"
    assert result.usage is None


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

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
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
    """本地编码发给模型时丢掉助手 `reasoning`，只保留正文。"""
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
    assert "reasoning_content" not in messages[0]


def test_dashscope_assistant_reasoning_encoded(settings: Settings) -> None:
    """`dashscope` 把思考写成独立 `reasoning_content`，不拼进正文。"""
    settings.provider = "dashscope"
    messages = to_chat_messages(
        [
            {
                "role": "assistant",
                "content": {"text": "你好", "reasoning": "先问候"},
            }
        ],
        settings=settings,
    )
    assert messages[0]["content"] == "你好"
    assert messages[0]["reasoning_content"] == "先问候"


def test_dashscope_assistant_without_reasoning_omits_field(settings: Settings) -> None:
    """`dashscope` 助手无思考时不加 `reasoning_content`。"""
    settings.provider = "dashscope"
    messages = to_chat_messages(
        [{"role": "assistant", "content": {"text": "你好"}}],
        settings=settings,
    )
    assert messages[0]["content"] == "你好"
    assert "reasoning_content" not in messages[0]


async def test_stream_http_error_includes_status(settings: Settings) -> None:
    """流式非 2xx 读出正文，错误含状态码且不含 httpx 内部文案。"""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "payload too large"})

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    try:
        await client.stream([{"role": "user", "content": "hi"}])
    except RuntimeError as exc:
        message = str(exc)
        assert "400" in message
        assert "without having called read" not in message
        assert "payload too large" in message
        return
    raise AssertionError("expected RuntimeError")


async def test_modelscope_connection_omits_serve(settings: Settings) -> None:
    """魔搭后端连不上时不提示 `max-gui serve`。"""
    settings.provider = "modelscope"
    settings.api_key = "tok"
    settings.model_name = "Qwen/Qwen3.8-27B"
    client = InferenceClient(settings)
    try:
        await client.stream([{"role": "user", "content": "hi"}])
    except ConnectionFailedError as exc:
        assert "max-gui serve" not in str(exc)
        assert "MAX_MODELSCOPE_KEY" in str(exc)
        return
    raise AssertionError("expected ConnectionFailedError")


async def test_modelscope_missing_key_skips_http(settings: Settings) -> None:
    """缺 `MAX_MODELSCOPE_KEY` 时不发请求。"""
    settings.provider = "modelscope"
    settings.api_key = ""
    settings.model_name = "Qwen/Qwen3.8-27B"

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not send HTTP without key")

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    try:
        await client.stream([{"role": "user", "content": "hi"}])
    except MissingProviderKeyError as exc:
        assert "max-gui serve" not in str(exc)
        return
    raise AssertionError("expected MissingProviderKeyError")


async def test_modelscope_sends_registered_model_id(settings: Settings, tmp_path: Path) -> None:
    """魔搭请求使用注册表中的模型标识。"""
    settings.provider = "modelscope"
    settings.api_key = "tok"
    settings.model_name = "Qwen/Qwen3.8-27B"
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen["model"] = payload["model"]
        seen["tools"] = payload.get("tools")
        seen["tool_choice"] = payload.get("tool_choice")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(["ok"]).encode(),
        )

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    tools = [{"type": "function", "function": {"name": "screenshot", "parameters": {}}}]
    result = await client.stream([{"role": "user", "content": "hi"}], tools=tools)
    assert result.text == "ok"
    assert seen["model"] == "Qwen/Qwen3.8-27B"
    assert seen["tools"] == tools
    assert seen["tool_choice"] == "auto"


async def test_openrouter_sends_registered_model_key_and_tools(
    settings: Settings, tmp_path: Path
) -> None:
    """OpenRouter 复用统一兼容请求，并发送固定模型、Bearer 密钥和工具。"""
    definition = PROVIDERS["openrouter"]
    settings.provider = definition.name
    settings.base_url = definition.base_url
    settings.model_name = definition.model_name
    settings.api_key = "or-token"
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        seen["model"] = payload["model"]
        seen["tools"] = payload.get("tools")
        seen["tool_choice"] = payload.get("tool_choice")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(["ok"]).encode(),
        )

    tools = [{"type": "function", "function": {"name": "screenshot", "parameters": {}}}]
    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    result = await client.stream([{"role": "user", "content": "hi"}], tools=tools)
    assert result.text == "ok"
    assert seen == {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "authorization": "Bearer or-token",
        "model": "qwen/qwen3.5-plus",
        "tools": tools,
        "tool_choice": "auto",
    }


def _sse_tool_calls() -> str:
    """两段 `tool_calls` 增量拼成一次调用。"""
    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "screenshot", "arguments": ""},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        },
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [{"index": 0, "function": {"name": "", "arguments": "{}"}}]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        },
    ]
    lines = [f"data: {json.dumps(item)}" for item in chunks]
    lines.append("data: [DONE]")
    return "\n".join(lines) + "\n"


def _configure_dashscope(settings: Settings, tmp_path: Path) -> None:
    """把夹具改成可用的 `dashscope` 配置。"""
    settings.provider = "dashscope"
    settings.api_key = "sk-tok"
    settings.model_name = PROVIDERS["dashscope"].model_name


async def test_dashscope_connection_omits_serve(settings: Settings, tmp_path: Path) -> None:
    """DashScope 后端连不上时不提示 `max-gui serve`。"""
    _configure_dashscope(settings, tmp_path)
    client = InferenceClient(settings)
    try:
        await client.stream([{"role": "user", "content": "hi"}])
    except ConnectionFailedError as exc:
        message = str(exc)
        assert "max-gui serve" not in message
        assert "MAX_DASHSCOPE_KEY" in message
        return
    raise AssertionError("expected ConnectionFailedError")


async def test_dashscope_missing_key_skips_http(settings: Settings, tmp_path: Path) -> None:
    """`dashscope` 缺密钥时不发请求。"""
    _configure_dashscope(settings, tmp_path)
    settings.api_key = ""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not send HTTP without key")

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    try:
        await client.stream([{"role": "user", "content": "hi"}])
    except MissingProviderKeyError as exc:
        assert "max-gui serve" not in str(exc)
        return
    raise AssertionError("expected MissingProviderKeyError")


async def test_dashscope_sends_registered_model_id(settings: Settings, tmp_path: Path) -> None:
    """DashScope 请求使用注册表端点与模型。"""
    _configure_dashscope(settings, tmp_path)
    settings.base_url = PROVIDERS["dashscope"].base_url
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen["url"] = str(request.url)
        seen["model"] = payload["model"]
        seen["tools"] = payload.get("tools")
        seen["tool_choice"] = payload.get("tool_choice")
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse(["ok"]).encode(),
        )

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    tools = [{"type": "function", "function": {"name": "screenshot", "parameters": {}}}]
    result = await client.stream([{"role": "user", "content": "hi"}], tools=tools)
    assert result.text == "ok"
    assert seen["model"] == "qwen3.8-27b"
    assert seen["tools"] == tools
    assert seen["tool_choice"] == "auto"
    assert seen["url"] == f"{PROVIDERS['dashscope'].base_url}/chat/completions"


async def test_dashscope_assembles_tool_calls(settings: Settings, tmp_path: Path) -> None:
    """DashScope 兼容 SSE 的 `tool_calls` 增量拼成完整调用。"""
    _configure_dashscope(settings, tmp_path)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_tool_calls().encode(),
        )

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    result = await client.stream(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "screenshot"}}],
    )
    assert result.tool_calls == [
        {"id": "call_1", "type": "function", "function": {"name": "screenshot", "arguments": "{}"}}
    ]


async def test_modelscope_assembles_tool_calls(settings: Settings) -> None:
    """魔搭兼容 SSE 的 `tool_calls` 增量拼成完整调用。"""
    settings.provider = "modelscope"
    settings.api_key = "tok"
    settings.model_name = "Qwen/Qwen3.8-27B"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=_sse_tool_calls().encode(),
        )

    client = InferenceClient(settings, transport=httpx.MockTransport(handler))
    result = await client.stream(
        [{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "function": {"name": "screenshot"}}],
    )
    assert result.tool_calls == [
        {"id": "call_1", "type": "function", "function": {"name": "screenshot", "arguments": "{}"}}
    ]


def test_explicit_task_image_selection_overrides_message_order(
    settings: Settings, tmp_path: Path
) -> None:
    """任务胶囊指定截图时，即使它不是最后一张也只内联该图。"""
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (20, 20), color="red").save(first)
    Image.new("RGB", (20, 20), color="blue").save(second)
    messages = [
        {"role": "user", "content": {"text": "任务", "images": [{"path": str(first)}]}},
        {"role": "tool", "content": {"text": "新截图", "images": [{"path": str(second)}]}},
    ]
    encoded = to_chat_messages(messages, settings=settings, inline_image_path=str(first))
    first_parts = encoded[0]["content"]
    second_parts = encoded[1]["content"]
    assert any(part["type"] == "image_url" for part in first_parts)
    assert isinstance(second_parts, str)
    assert "历史截图已省略" in second_parts
