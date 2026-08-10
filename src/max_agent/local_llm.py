"""本地聊天模型的发现、完整性校验、延迟加载与会话状态管理。"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MODEL_NAME = "Qwen/Qwen3.5-2B"
MODEL_ROOT = Path("model")
REQUIRED_MODEL_FILES = ("config.json", "tokenizer.json", "model.safetensors.index.json")
QWEN35_2B_MODEL_ID = "Qwen/Qwen3.5-2B"
QWEN35_2B_MODEL_PATH = MODEL_ROOT / QWEN35_2B_MODEL_ID


class LocalRuntimeError(RuntimeError):
    """将底层加载或生成失败转换为可直接呈现给用户的本地运行时错误。"""

    pass


def discover_local_models(repository_root: Path) -> tuple[str, ...]:
    """发现 `model/` 内含配置文件的模型目录，并返回稳定排序的相对名称。"""
    model_root = (repository_root / MODEL_ROOT).resolve()
    if not model_root.is_dir():
        return ()
    names = {
        config.parent.resolve().relative_to(model_root).as_posix()
        for config in model_root.rglob("config.json")
        if config.parent.resolve().is_relative_to(model_root)
    }
    return tuple(sorted(names))


def require_local_model(repository_root: Path, model_name: str) -> Path:
    """校验选定模型位于受管目录且配置、索引和全部权重均完整。"""
    if model_name not in discover_local_models(repository_root):
        raise LocalRuntimeError(f"本地模型不可选择：{model_name}")
    model_dir = ((repository_root / MODEL_ROOT) / Path(model_name)).resolve()
    missing = [
        name for name in REQUIRED_MODEL_FILES if not (model_dir / name).is_file()
    ]
    if missing:
        raise LocalRuntimeError(
            f"本地模型不完整：{model_name}，缺少 {', '.join(missing)}"
        )
    try:
        weights = set(
            json.loads(
                (model_dir / "model.safetensors.index.json").read_text(encoding="utf-8")
            )["weight_map"].values()
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        raise LocalRuntimeError(f"本地模型权重索引无效：{model_name}") from None
    if not weights or any(not (model_dir / name).is_file() for name in weights):
        raise LocalRuntimeError(f"本地模型权重不完整：{model_name}")
    return model_dir


def require_qwen35_2b(repository_root: Path) -> Path:
    """兼容调用方对默认 Qwen3.5-2B 模型的显式校验入口。"""
    return require_local_model(repository_root, DEFAULT_MODEL_NAME)


def _load_local_model(model_dir: Path) -> tuple[object, object]:
    """仅在满足 CUDA BF16 条件时离线装载模型及其处理器。"""
    import torch
    from transformers import AutoModelForMultimodalLM, AutoProcessor

    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise LocalRuntimeError("本地聊天需要支持 BF16 的 CUDA GPU；请先运行 /doctor。")
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
            raise LocalRuntimeError("GPU 显存不足，无法加载当前本地模型。") from None
        raise LocalRuntimeError(
            "本地模型加载失败；请运行 /doctor 或选择其他模型。"
        ) from None


def _generate(
    model: object, processor: object, history: list[dict[str, str]], message: str
) -> str:
    """将历史和新消息组成模型模板，并仅解码本轮新增 token。"""
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
                "生成时 GPU 显存不足，请缩短会话或选择其他模型。"
            ) from None
        raise LocalRuntimeError(
            "本地模型生成失败；会话仍可使用 /model、/doctor 或 /quit。"
        ) from None


@dataclass
class LocalChatRuntime:
    """按需加载单个本地模型，并维护可在模型切换时清空的会话历史。"""

    repository_root: Path
    selected_model: str = DEFAULT_MODEL_NAME
    loader: Callable[[Path], tuple[object, object]] = _load_local_model
    generator: Callable[[object, object, list[dict[str, str]], str], str] = _generate
    state: str = field(default="unloaded", init=False)
    _model: object | None = field(default=None, init=False)
    _processor: object | None = field(default=None, init=False)
    _history: list[dict[str, str]] = field(default_factory=list, init=False)

    def available_models(self) -> tuple[str, ...]:
        """返回当前仓库中可供交互选择的完整模型。"""
        return discover_local_models(self.repository_root)

    def select_model(self, model_name: str) -> None:
        """切换模型并重置缓存与历史，避免不同模型共享上下文。"""
        selected = model_name.strip()
        if selected not in self.available_models():
            raise LocalRuntimeError(f"本地模型不可选择：{selected}")
        if selected == self.selected_model:
            return
        self.selected_model = selected
        self.state = "unloaded"
        self._model = None
        self._processor = None
        self._history.clear()

    def reply(self, message: str) -> str:
        """延迟加载当前模型、生成回复，并仅在成功后写入会话历史。"""
        if self.state == "failed":
            self.state = "unloaded"
        if self._model is None or self._processor is None:
            self.state = "loading"
            try:
                self._model, self._processor = self.loader(
                    require_local_model(self.repository_root, self.selected_model)
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

    def explain_image(self, goal: str, image: object) -> str:
        if self._model is None or self._processor is None:
            self.reply("Prepare the local model for a visual explanation.")
        import torch

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": goal},
                ],
            }
        ]
        try:
            rendered = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self._processor(
                text=[rendered], images=[image], padding=True, return_tensors="pt"
            ).to("cuda")
            with torch.inference_mode():
                output = self._model.generate(**inputs, max_new_tokens=256)
            return self._processor.batch_decode(
                output[:, inputs.input_ids.shape[1] :], skip_special_tokens=True
            )[0]
        except (AttributeError, RuntimeError, ValueError, TypeError) as error:
            raise LocalRuntimeError(f"本地模型无法解释图像：{error}") from None
