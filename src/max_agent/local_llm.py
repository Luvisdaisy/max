from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

QWEN35_2B_MODEL_ID = "Qwen/Qwen3.5-2B"
QWEN35_2B_MODEL_PATH = Path("model/Qwen/Qwen3.5-2B")


class LocalRuntimeError(RuntimeError):
    pass


def require_qwen35_2b(repository_root: Path) -> Path:
    model_dir = (repository_root / QWEN35_2B_MODEL_PATH).resolve()
    required = ("config.json", "tokenizer.json", "model.safetensors.index.json")
    if any(not (model_dir / name).is_file() for name in required):
        raise LocalRuntimeError(
            "本地 Qwen3.5-2B 不完整；请确认 model/Qwen/Qwen3.5-2B 已完整下载。"
        )
    try:
        weights = set(
            json.loads(
                (model_dir / "model.safetensors.index.json").read_text(encoding="utf-8")
            )["weight_map"].values()
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        raise LocalRuntimeError(
            "本地 Qwen3.5-2B 权重索引无效；请重新完成本地下载。"
        ) from None
    if not weights or any(not (model_dir / name).is_file() for name in weights):
        raise LocalRuntimeError("本地 Qwen3.5-2B 权重不完整；请重新完成本地下载。")
    return model_dir


def _load_qwen35_2b(model_dir: Path) -> tuple[object, object]:
    import torch
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise LocalRuntimeError(
            "本地聊天需要支持 BF16 的 CUDA GPU；请先在 Textual 中运行 /doctor。"
        )
    try:
        model = (
            AutoModelForMultimodalLM.from_pretrained(
                str(model_dir), dtype=torch.bfloat16, local_files_only=True
            )
            .to("cuda")
            .eval()
        )
        return model, AutoProcessor.from_pretrained(
            str(model_dir), local_files_only=True
        )
    except RuntimeError as error:
        if "out of memory" in str(error).lower():
            raise LocalRuntimeError(
                "GPU 显存不足，无法加载 Qwen3.5-2B；请关闭其他 CUDA 程序后重试。"
            ) from None
        raise LocalRuntimeError(
            "本地 Qwen3.5-2B 加载失败；请在 /doctor 中检查运行环境。"
        ) from None


def _generate(
    model: object, processor: object, history: list[dict[str, str]], message: str
) -> str:
    import torch

    messages = [*history, {"role": "user", "content": message}]
    rendered = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = processor(text=[rendered], padding=True, return_tensors="pt").to("cuda")
    try:
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=128)
        return processor.batch_decode(
            output[:, inputs.input_ids.shape[1] :], skip_special_tokens=True
        )[0]
    except RuntimeError as error:
        if "out of memory" in str(error).lower():
            raise LocalRuntimeError(
                "生成时 GPU 显存不足；请缩短会话或关闭其他 CUDA 程序后重试。"
            ) from None
        raise LocalRuntimeError(
            "本地模型生成失败；会话仍可继续使用 /doctor 或 /quit。"
        ) from None


@dataclass
class LocalChatRuntime:
    repository_root: Path
    loader: Callable[[Path], tuple[object, object]] = _load_qwen35_2b
    generator: Callable[[object, object, list[dict[str, str]], str], str] = _generate
    state: str = field(default="unloaded", init=False)
    _model: object | None = field(default=None, init=False)
    _processor: object | None = field(default=None, init=False)
    _history: list[dict[str, str]] = field(default_factory=list, init=False)

    def reply(self, message: str) -> str:
        if self.state == "failed":
            self.state = "unloaded"
        if self._model is None or self._processor is None:
            self.state = "loading"
            try:
                self._model, self._processor = self.loader(
                    require_qwen35_2b(self.repository_root)
                )
                self.state = "ready"
            except LocalRuntimeError:
                self.state = "failed"
                raise
        try:
            response = self.generator(
                self._model, self._processor, self._history, message
            )
        except LocalRuntimeError:
            self.state = "failed"
            raise
        self._history.extend(
            (
                {"role": "user", "content": message},
                {"role": "assistant", "content": response},
            )
        )
        return response
