"""运行时配置：模型别名、路径探测、环境变量与权重校验。"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

DEFAULT_MODEL_ALIAS = "qwen3.5-4b"

# 产品别名 -> 规范目录名（位于 model/ 下）
MODEL_ALIASES: dict[str, str] = {
    "qwen3.5-2b": "qwen3.5-2b",
    "qwen2b": "qwen3.5-2b",
    "2b": "qwen3.5-2b",
    "qwen3.5-4b": "qwen3.5-4b",
    "qwen4b": "qwen3.5-4b",
    "4b": "qwen3.5-4b",
    "qwen3.5-9b": "qwen3.5-9b",
    "qwen9b": "qwen3.5-9b",
    "9b": "qwen3.5-9b",
}

MODELSCOPE_IDS: dict[str, str] = {
    "qwen3.5-2b": "Qwen/Qwen3.5-2B",
    "qwen3.5-4b": "Qwen/Qwen3.5-4B",
    "qwen3.5-9b": "Qwen/Qwen3.5-9B",
}


class UnknownModelError(ValueError):
    """用户给出的模型别名不在 `MODEL_ALIASES` 中。"""


class MissingWeightsError(FileNotFoundError):
    """本地权重目录不完整，提示先执行下载命令。"""

    def __init__(self, alias: str, download_cmd: str) -> None:
        """参数：`alias` 规范模型名；`download_cmd` 建议用户执行的命令。"""
        self.alias = alias
        self.download_cmd = download_cmd
        super().__init__(f"模型权重缺失：{alias}。请先运行：{download_cmd}")


DEFAULT_VLLM_BIN = Path.home() / ".venv-vllm-metal" / "bin" / "vllm"
DEFAULT_OCR_MODEL = "paddleocr-vl-1.5"
DEFAULT_OCR_BASE_URL = "http://127.0.0.1:8001/v1"


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


def resolve_model_alias(raw: str) -> str:
    """把产品别名规范成 `model/` 下的目录名。

    参数：
        raw: 如 `2b`、`qwen2b`、`qwen3.5-2b`。

    返回：
        规范目录名。

    异常：
        UnknownModelError: 别名未知。
    """
    key = raw.strip().lower()
    if key not in MODEL_ALIASES:
        known = ", ".join(sorted(set(MODEL_ALIASES.values())))
        raise UnknownModelError(f"未知模型别名：{raw}。可用：{known}")
    return MODEL_ALIASES[key]


def download_command(alias: str) -> str:
    """生成下载该别名的 CLI 提示，例如 `max-gui download qwen3.5-2b`。"""
    canonical = resolve_model_alias(alias)
    return f"max-gui download {canonical}"


@dataclass(slots=True)
class Settings:
    """一次运行所需的路径、推理端点与限制。

    字段由 `load_settings` 从环境变量填充；`with_model` 只替换模型别名。
    """

    base_url: str = "http://127.0.0.1:8000/v1"
    api_key: str = "EMPTY"
    model_alias: str = DEFAULT_MODEL_ALIAS
    project_root: Path = Path(".")
    workspace: Path = Path(".")
    sessions_dir: Path = Path("artifacts/sessions")
    screenshots_dir: Path = Path("artifacts/screenshots")
    model_root: Path = Path("model")
    max_iterations: int = 8
    max_image_edge: int = 1536
    max_image_bytes: int = 2_000_000
    tool_timeout: float = 30.0
    max_model_len: int = 8192
    gpu_memory_utilization: float = 0.85
    dtype: str = "auto"
    ocr_base_url: str = DEFAULT_OCR_BASE_URL
    ocr_start_timeout: float = 180.0
    ocr_timeout: float = 120.0
    ocr_gpu_memory_utilization: float = 0.20

    @property
    def canonical_model(self) -> str:
        """当前别名对应的规范模型目录名。"""
        return resolve_model_alias(self.model_alias)

    @property
    def model_path(self) -> Path:
        """本地权重目录：`model_root / canonical_model`。"""
        return self.model_root / self.canonical_model

    @property
    def ocr_model_path(self) -> Path:
        """PaddleOCR-VL 权重目录：`model_root / paddleocr-vl-1.5`。"""
        return self.model_root / DEFAULT_OCR_MODEL

    def with_model(self, alias: str) -> Settings:
        """返回只替换模型别名为规范名的新配置。"""
        return replace(self, model_alias=resolve_model_alias(alias))


def load_settings(
    *,
    workspace: Path | None = None,
    model: str | None = None,
    sessions_dir: Path | None = None,
    base_url: str | None = None,
) -> Settings:
    """从参数与环境变量组装 `Settings`。

    环境变量：`MAX_GUI_MODEL`、`MAX_GUI_BASE_URL`、`MAX_GUI_API_KEY`、
    `MAX_GUI_WORKSPACE`、`MAX_GUI_MAX_ITERATIONS`、`MAX_GUI_MAX_IMAGE_*`、
    `MAX_GUI_TOOL_TIMEOUT`、`MAX_GUI_MAX_MODEL_LEN`、`MAX_GUI_GPU_MEM`、
    `MAX_GUI_DTYPE`、`MAX_GUI_OCR_BASE_URL`、`MAX_GUI_OCR_START_TIMEOUT`、
    `MAX_GUI_OCR_TIMEOUT`、`MAX_GUI_OCR_GPU_MEM`。

    参数：
        workspace: 工具读写根；缺省 `MAX_GUI_WORKSPACE` 或 cwd。
        model: 模型别名；缺省环境变量或 `DEFAULT_MODEL_ALIAS`。
        sessions_dir: 会话 JSON 目录；缺省 `<root>/artifacts/sessions`。
        base_url: OpenAI 兼容端点；缺省本机 8000。

    返回：
        解析后的配置。
    """
    root = detect_project_root()
    alias = resolve_model_alias(model or os.environ.get("MAX_GUI_MODEL") or DEFAULT_MODEL_ALIAS)
    settings = Settings(
        base_url=base_url or os.environ.get("MAX_GUI_BASE_URL") or "http://127.0.0.1:8000/v1",
        api_key=os.environ.get("MAX_GUI_API_KEY") or "EMPTY",
        model_alias=alias,
        project_root=root,
        workspace=(workspace or Path(os.environ.get("MAX_GUI_WORKSPACE") or Path.cwd())).resolve(),
        sessions_dir=(sessions_dir or root / "artifacts" / "sessions").resolve(),
        screenshots_dir=(root / "artifacts" / "screenshots").resolve(),
        model_root=(root / "model").resolve(),
        max_iterations=int(os.environ.get("MAX_GUI_MAX_ITERATIONS") or 8),
        max_image_edge=int(os.environ.get("MAX_GUI_MAX_IMAGE_EDGE") or 1536),
        max_image_bytes=int(os.environ.get("MAX_GUI_MAX_IMAGE_BYTES") or 2_000_000),
        tool_timeout=float(os.environ.get("MAX_GUI_TOOL_TIMEOUT") or 30),
        max_model_len=int(os.environ.get("MAX_GUI_MAX_MODEL_LEN") or 8192),
        gpu_memory_utilization=float(os.environ.get("MAX_GUI_GPU_MEM") or 0.85),
        dtype=os.environ.get("MAX_GUI_DTYPE") or "auto",
        ocr_base_url=os.environ.get("MAX_GUI_OCR_BASE_URL") or DEFAULT_OCR_BASE_URL,
        ocr_start_timeout=float(os.environ.get("MAX_GUI_OCR_START_TIMEOUT") or 180),
        ocr_timeout=float(os.environ.get("MAX_GUI_OCR_TIMEOUT") or 120),
        ocr_gpu_memory_utilization=float(os.environ.get("MAX_GUI_OCR_GPU_MEM") or 0.20),
    )
    return settings


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


def require_weights(settings: Settings) -> Path:
    """确认当前模型权重可用。

    返回：
        权重目录。

    异常：
        MissingWeightsError: 目录缺失或不完整。
    """
    path = settings.model_path
    if not weights_ready(path):
        raise MissingWeightsError(
            settings.canonical_model, download_command(settings.canonical_model)
        )
    return path
