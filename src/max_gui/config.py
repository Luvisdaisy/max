"""运行时配置：`.env` 载入、provider 快照与 OCR / OmniParser 路径探测。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from max_gui.provider import DEFAULT_PROVIDER, PROVIDERS, resolve_provider

DEFAULT_VLLM_BIN = Path.home() / ".venv-vllm-metal" / "bin" / "vllm"
DEFAULT_OCR_MODEL = "paddleocr-vl-1.5"
DEFAULT_OCR_BASE_URL = "http://127.0.0.1:8001/v1"
DEFAULT_OMNIPARSER_DIR = "omniparserv2"
DEFAULT_OMNIPARSER_BASE_URL = "http://127.0.0.1:8002"
DEFAULT_MAX_OUTPUT_TOKENS = 8192
DEFAULT_CONTEXT_SAFETY_MARGIN = 4096
DEFAULT_IMAGE_TOKEN_RESERVE = 8192
DEFAULT_INFERENCE_MAX_RETRIES = 5


class InferenceRetryConfigError(ValueError):
    """主推理最大重试次数不是 0–5 的整数。"""

    def __init__(self, raw: object) -> None:
        """用非法配置原文构造不包含敏感信息的中文错误。"""
        super().__init__(f"MAX_GUI_INFERENCE_MAX_RETRIES 必须是 0–5 的整数，当前值：{raw!s}")


class EnableThinkingConfigError(ValueError):
    """上游 thinking 开关不是严格布尔值。"""

    def __init__(self, raw: object) -> None:
        """用非法配置原文构造不包含敏感信息的中文错误。"""
        super().__init__(f"MAX_GUI_ENABLE_THINKING 必须是 true 或 false，当前值：{raw!s}")


class ContextBudgetConfigError(ValueError):
    """主推理上下文容量与预留配置无法形成正的输入预算。"""

    def __init__(self, context_window: int, max_output_tokens: int, safety_margin: int) -> None:
        """用容量和两项预留构造不包含敏感内容的中文错误。"""
        super().__init__(
            "主推理上下文预算无效："
            f"容量 {context_window}，输出预留 {max_output_tokens}，安全余量 {safety_margin}。"
        )


class MissingVllmError(FileNotFoundError):
    """找不到独立 vLLM 可执行文件。"""

    def __init__(self) -> None:
        """文案提示激活 `~/.venv-vllm-metal` 或设置 `MAX_GUI_VLLM`。"""
        super().__init__(
            "找不到 vLLM 可执行文件。请先 `source ~/.venv-vllm-metal/bin/activate`，"
            "或设置 MAX_GUI_VLLM 指向 vllm 二进制"
            f"（默认路径：{DEFAULT_VLLM_BIN}）。"
        )


def detect_project_root() -> Path:
    """推断仓库根目录。

    优先 `MAX_GUI_ROOT`；否则在当前目录与本文件祖先中找同时含 `model/`
    与 `pyproject.toml` 的路径，再退化为仅含 `model/`，最后用 cwd。

    返回：
        解析后的根路径。
    """
    env = os.environ.get("MAX_GUI_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    cwd = Path.cwd()
    here = Path(__file__).resolve()
    candidates = [cwd, *here.parents]
    for path in candidates:
        if (path / "model").is_dir() and (path / "pyproject.toml").exists():
            return path
    for path in candidates:
        if (path / "model").is_dir():
            return path
    return cwd


def load_env_file(root: Path) -> None:
    """若 `root/.env` 存在则载入；已有进程环境变量不被覆盖。

    参数：
        root: 仓库根目录。
    """
    path = root / ".env"
    if path.is_file():
        load_dotenv(path, override=False)


@dataclass(slots=True)
class Settings:
    """一次运行所需的路径、推理端点与限制。

    字段通常由 `load_settings` 从 `.env` 与环境变量填充；`reasoning_effort` 供特定内部调用按
    provider 能力覆盖，默认不发送该字段。
    """

    provider: str = DEFAULT_PROVIDER
    base_url: str = PROVIDERS[DEFAULT_PROVIDER].base_url
    api_key: str = "EMPTY"
    model_name: str = PROVIDERS[DEFAULT_PROVIDER].model_name
    project_root: Path = Path(".")
    workspace: Path = Path(".")
    sessions_dir: Path = Path("artifacts/sessions")
    screenshots_dir: Path = Path("artifacts/screenshots")
    model_root: Path = Path("model")
    max_iterations: int = 20
    max_image_edge: int = 1536
    max_image_bytes: int = 2_000_000
    tool_timeout: float = 30.0
    max_model_len: int = 8192
    context_window: int = 262_144
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    context_safety_margin: int = DEFAULT_CONTEXT_SAFETY_MARGIN
    image_token_reserve: int = DEFAULT_IMAGE_TOKEN_RESERVE
    inference_max_retries: int = DEFAULT_INFERENCE_MAX_RETRIES
    enable_thinking: bool = False
    reasoning_effort: Literal["low", "high", "max"] | None = None
    dtype: str = "auto"
    ocr_base_url: str = DEFAULT_OCR_BASE_URL
    ocr_start_timeout: float = 180.0
    ocr_timeout: float = 120.0
    ocr_gpu_memory_utilization: float = 0.20
    omniparser_dir: str = DEFAULT_OMNIPARSER_DIR
    omniparser_base_url: str = DEFAULT_OMNIPARSER_BASE_URL
    omniparser_start_timeout: float = 180.0
    omniparser_timeout: float = 120.0

    @property
    def ocr_model_path(self) -> Path:
        """PaddleOCR-VL 权重目录：`model_root / paddleocr-vl-1.5`。"""
        return self.model_root / DEFAULT_OCR_MODEL

    @property
    def omniparser_model_path(self) -> Path:
        """OmniParser 权重目录：`model_root / omniparser_dir`，默认 `omniparserv2`。"""
        return self.model_root / self.omniparser_dir


def load_settings(
    *,
    workspace: Path | None = None,
    sessions_dir: Path | None = None,
) -> Settings:
    """从 `.env` 与环境变量组装 `Settings`。

    先按 `detect_project_root` 定位根目录并载入 `.env`（不覆盖已有环境变量）。
    环境变量：`MAX_PROVIDER`、`MAX_MODELSCOPE_KEY`、`MAX_DASHSCOPE_KEY`、
    `MAX_OPENROUTER_KEY`、`MAX_QINIU_KEY`、`MAX_GUI_WORKSPACE`、
    `MAX_GUI_MAX_ITERATIONS`、`MAX_GUI_MAX_IMAGE_*`、`MAX_GUI_TOOL_TIMEOUT`、
    `MAX_GUI_MAX_MODEL_LEN`、`MAX_GUI_MAX_OUTPUT_TOKENS`、
    `MAX_GUI_CONTEXT_SAFETY_MARGIN`、`MAX_GUI_INFERENCE_MAX_RETRIES`、
    `MAX_GUI_ENABLE_THINKING`、
    `MAX_GUI_DTYPE`、`MAX_GUI_OCR_*`、
    `MAX_GUI_OMNIPARSER_*`。
    provider 的模型、端点与能力来自 `max_gui.provider`；不读取旧共享键、
    `MODEL_NAME` 或 provider 专属 SDK 键。

    参数：
        workspace: 工具读写根；缺省 `MAX_GUI_WORKSPACE` 或 cwd。
        sessions_dir: 会话 JSON 目录；缺省 `<root>/artifacts/sessions`。

    返回：
        解析后的配置。

    异常：
        UnknownProviderError: `MAX_PROVIDER` 非法，由 provider 模块抛出。
        InferenceRetryConfigError: 主推理重试次数不是 0–5 的整数。
        EnableThinkingConfigError: 上游 thinking 开关不是 true 或 false。
        ContextBudgetConfigError: 主推理上下文预留无法形成正的输入预算。
    """
    root = detect_project_root()
    load_env_file(root)
    provider = resolve_provider(os.environ.get("MAX_PROVIDER"))
    max_model_len = int(os.environ.get("MAX_GUI_MAX_MODEL_LEN") or 8192)
    context_window = provider.context_window
    max_output_tokens = int(
        os.environ.get("MAX_GUI_MAX_OUTPUT_TOKENS") or DEFAULT_MAX_OUTPUT_TOKENS
    )
    retry_raw = os.environ.get("MAX_GUI_INFERENCE_MAX_RETRIES")
    try:
        inference_max_retries = (
            DEFAULT_INFERENCE_MAX_RETRIES if retry_raw is None else int(retry_raw)
        )
    except ValueError as exc:
        raise InferenceRetryConfigError(retry_raw) from exc
    if not 0 <= inference_max_retries <= 5:
        raise InferenceRetryConfigError(retry_raw)
    enable_thinking = _parse_enable_thinking(os.environ.get("MAX_GUI_ENABLE_THINKING"))
    context_safety_margin = int(
        os.environ.get("MAX_GUI_CONTEXT_SAFETY_MARGIN") or DEFAULT_CONTEXT_SAFETY_MARGIN
    )
    if (
        context_window <= 0
        or max_output_tokens <= 0
        or context_safety_margin <= 0
        or max_output_tokens + context_safety_margin >= context_window
    ):
        raise ContextBudgetConfigError(context_window, max_output_tokens, context_safety_margin)
    api_key = (
        (os.environ.get(provider.api_key_env) or "").strip()
        if provider.api_key_env is not None
        else "EMPTY"
    )
    settings = Settings(
        provider=provider.name,
        base_url=provider.base_url,
        api_key=api_key,
        model_name=provider.model_name,
        project_root=root,
        workspace=(workspace or Path(os.environ.get("MAX_GUI_WORKSPACE") or Path.cwd())).resolve(),
        sessions_dir=(sessions_dir or root / "artifacts" / "sessions").resolve(),
        screenshots_dir=(root / "artifacts" / "screenshots").resolve(),
        model_root=(root / "model").resolve(),
        max_iterations=int(os.environ.get("MAX_GUI_MAX_ITERATIONS") or 20),
        max_image_edge=int(os.environ.get("MAX_GUI_MAX_IMAGE_EDGE") or 1536),
        max_image_bytes=int(os.environ.get("MAX_GUI_MAX_IMAGE_BYTES") or 2_000_000),
        tool_timeout=float(os.environ.get("MAX_GUI_TOOL_TIMEOUT") or 30),
        max_model_len=max_model_len,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        context_safety_margin=context_safety_margin,
        inference_max_retries=inference_max_retries,
        enable_thinking=enable_thinking,
        dtype=os.environ.get("MAX_GUI_DTYPE") or "auto",
        ocr_base_url=os.environ.get("MAX_GUI_OCR_BASE_URL") or DEFAULT_OCR_BASE_URL,
        ocr_start_timeout=float(os.environ.get("MAX_GUI_OCR_START_TIMEOUT") or 180),
        ocr_timeout=float(os.environ.get("MAX_GUI_OCR_TIMEOUT") or 120),
        ocr_gpu_memory_utilization=float(os.environ.get("MAX_GUI_OCR_GPU_MEM") or 0.20),
        omniparser_dir=(os.environ.get("MAX_GUI_OMNIPARSER_DIR") or DEFAULT_OMNIPARSER_DIR).strip(),
        omniparser_base_url=os.environ.get("MAX_GUI_OMNIPARSER_BASE_URL")
        or DEFAULT_OMNIPARSER_BASE_URL,
        omniparser_start_timeout=float(os.environ.get("MAX_GUI_OMNIPARSER_START_TIMEOUT") or 180),
        omniparser_timeout=float(os.environ.get("MAX_GUI_OMNIPARSER_TIMEOUT") or 120),
    )
    return settings


def _parse_enable_thinking(raw: str | None) -> bool:
    """解析严格布尔的上游 thinking 开关。

    参数：
        raw: 环境变量原文；未设置或空白时缺省关闭。

    返回：
        `true` 对应真，`false` 或空值对应假。

    异常：
        EnableThinkingConfigError: 非空值不是 true 或 false。
    """
    value = (raw or "").strip().lower()
    if not value or value == "false":
        return False
    if value == "true":
        return True
    raise EnableThinkingConfigError(raw)


def weights_ready(path: Path) -> bool:
    """目录是否含完整权重（存在 `.safetensors` 或 `.bin`，且无 `.incomplete`）。"""
    if not path.is_dir():
        return False
    weights = list(path.glob("*.safetensors")) + list(path.glob("*.bin"))
    if not weights:
        return False
    return not any(
        p.suffix == ".incomplete" or p.name.endswith(".incomplete") for p in path.iterdir()
    )
