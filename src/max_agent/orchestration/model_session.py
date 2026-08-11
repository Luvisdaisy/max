"""离线本地模型的 text-or-tool 会话协议与严格解析。"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

from pydantic import TypeAdapter, ValidationError

from max_agent.local_llm import (
    LocalRuntimeError,
    _load_local_model,
    require_local_model,
)
from max_agent.orchestration.models import (
    AgentMessage,
    FinalTextResponse,
    ModelTurnResponse,
    ToolUseResponse,
)


class AgentModelError(RuntimeError):
    """模型不可用或连续返回无效结构。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AgentModelSession(Protocol):
    """前端无关且不依赖 LocalChatRuntime 历史的模型轮次协议。"""

    def respond(
        self,
        messages: Sequence[AgentMessage],
        tools: Sequence[dict[str, object]],
        *,
        reasoning_mode: str = "fast",
        images: Sequence[object] = (),
        consume_correction: Callable[[], bool] | None = None,
    ) -> ModelTurnResponse: ...

    def reset(self) -> None: ...


RawResponder = Callable[
    [Sequence[AgentMessage], Sequence[dict[str, object]], str, Sequence[object]], str
]


class LocalAgentModelSession:
    """按当前模型名称懒加载一个离线模型，并严格区分文本与工具调用。"""

    def __init__(
        self,
        repository_root: Path,
        selected_model: Callable[[], str],
        responder: RawResponder | None = None,
    ) -> None:
        self._repository_root = repository_root
        self._selected_model = selected_model
        self._responder = responder
        self._loaded_name: str | None = None
        self._model: object | None = None
        self._processor: object | None = None

    def reset(self) -> None:
        self._loaded_name = None
        self._model = None
        self._processor = None

    def respond(
        self,
        messages: Sequence[AgentMessage],
        tools: Sequence[dict[str, object]],
        *,
        reasoning_mode: str = "fast",
        images: Sequence[object] = (),
        consume_correction: Callable[[], bool] | None = None,
    ) -> ModelTurnResponse:
        selected_messages = _trim_messages(messages, reasoning_mode)
        raw = self._call(selected_messages, tools, reasoning_mode, images)
        try:
            return parse_model_response(raw)
        except AgentModelError as first_error:
            if consume_correction is not None and not consume_correction():
                raise AgentModelError(
                    "CORRECTION_BUDGET_EXHAUSTED", "model correction budget exhausted"
                ) from None
            correction = AgentMessage(
                role="user",
                content=(
                    "上一个响应不符合协议。只能返回面向用户的纯文本，或完整 JSON "
                    '{"type":"tool_use","tool_name":"...","arguments":{...}}。'
                    f"错误：{first_error}"
                ),
            )
            corrected = self._call(
                [*selected_messages, correction], tools, reasoning_mode, images
            )
            try:
                return parse_model_response(corrected)
            except AgentModelError:
                raise AgentModelError(
                    "INVALID_MODEL_RESPONSE",
                    "model response remained invalid after correction",
                ) from None

    def _call(
        self,
        messages: Sequence[AgentMessage],
        tools: Sequence[dict[str, object]],
        reasoning_mode: str,
        images: Sequence[object],
    ) -> str:
        if self._responder is not None:
            return self._responder(messages, tools, reasoning_mode, images)
        name = self._selected_model()
        if self._loaded_name != name or self._model is None or self._processor is None:
            self.reset()
            try:
                self._model, self._processor = _load_local_model(
                    require_local_model(self._repository_root, name)
                )
            except LocalRuntimeError as error:
                raise AgentModelError("MODEL_UNAVAILABLE", str(error)) from None
            self._loaded_name = name
        return _generate_turn(
            self._model, self._processor, messages, tools, reasoning_mode, images
        )


def parse_model_response(raw: str) -> ModelTurnResponse:
    """纯文本直接结束；只有完整 JSON 对象可表达单个工具调用。"""
    response = raw.strip()
    if not response:
        raise AgentModelError("INVALID_MODEL_RESPONSE", "model returned empty text")
    if response.startswith("["):
        raise AgentModelError(
            "INVALID_MODEL_RESPONSE", "multiple tool calls are not allowed"
        )
    if not response.startswith("{"):
        return FinalTextResponse(text=response)
    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        raise AgentModelError("INVALID_MODEL_RESPONSE", "invalid tool JSON") from None
    try:
        return TypeAdapter(ToolUseResponse).validate_python(payload)
    except ValidationError as error:
        raise AgentModelError(
            "INVALID_MODEL_RESPONSE", str(error.errors()[0]["msg"])
        ) from None


def _generate_turn(
    model: object,
    processor: object,
    messages: Sequence[AgentMessage],
    tools: Sequence[dict[str, object]],
    reasoning_mode: str,
    images: Sequence[object],
) -> str:
    """构造本地 chat template；系统只请求最终文本或单工具 JSON。"""
    import torch

    system = (
        "你是 MAX 的受控桌面 Agent。无需工具时直接回复最终文本；需要工具时只返回一个完整 JSON："
        '{"type":"tool_use","tool_name":"名称","arguments":{...},"audit_summary":"简短理由"}。'
        "不得输出 Thought/Plan/Action 标签，不得调用未列出的工具。"
        f"当前模式：{reasoning_mode}。可用工具：{json.dumps(list(tools), ensure_ascii=False)}"
    )
    rendered_messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for message in messages:
        content = (
            message.content
            if isinstance(message.content, str)
            else json.dumps(message.content, ensure_ascii=False)
        )
        rendered_messages.append({"role": message.role.value, "content": content})
    rendered = processor.apply_chat_template(
        rendered_messages, tokenize=False, add_generation_prompt=True
    )
    kwargs: dict[str, Any] = {
        "text": [rendered],
        "padding": True,
        "return_tensors": "pt",
    }
    if images:
        kwargs["images"] = list(images)
    inputs = processor(**kwargs).to("cuda")
    try:
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=256)
        return processor.batch_decode(
            output[:, inputs.input_ids.shape[1] :], skip_special_tokens=True
        )[0]
    except RuntimeError as error:
        code = (
            "MODEL_UNAVAILABLE"
            if "out of memory" in str(error).lower()
            else "MODEL_FAILED"
        )
        raise AgentModelError(code, "local model generation failed") from None


def _trim_messages(
    messages: Sequence[AgentMessage], reasoning_mode: str
) -> list[AgentMessage]:
    """保留初始用户目标和有限最近轮次，避免工具循环无限扩张上下文。"""
    limit = 24 if reasoning_mode == "deliberate" else 12
    if len(messages) <= limit:
        return list(messages)
    first_user = next(
        (message for message in messages if message.role.value == "user"), None
    )
    tail = list(messages[-(limit - 1) :])
    return (
        [first_user, *tail]
        if first_user is not None and first_user not in tail
        else list(messages[-limit:])
    )
