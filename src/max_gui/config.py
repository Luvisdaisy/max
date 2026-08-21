"""运行时配置：`.env` 载入、推理后端、路径探测与权重校验。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_PROVIDER = "local"
PROVIDERS = frozenset({"local", "modelscope"})
DEFAULT_LOCAL_MODEL = "qwen3.5-4b"
DEFAULT_MODELSCOPE_MODEL = "Qwen/Qwen3.8-27B"
MODELSCOPE_BASE_URL = "https://api-inference.modelscope.cn/v1"
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:8000/v1"

DEFAULT_VLLM_BIN = Path.home() / ".venv-vllm-metal" / "bin" / "vllm"
DEFAULT_OCR_MODEL = "paddleocr-vl-1.5"
DEFAULT_OCR_BASE_URL = "http://127.0.0.1:8001/v1"


class UnknownProviderError(ValueError):
    """`MAX_PROVIDER` 不是 `local` 或 `modelscope`。"""

    def __init__(self, raw: str) -> None:
        """参数：`raw` 为用户给出的非法值。"""
        super().__init__(f"未知推理后端：{raw}。可用：local, modelscope")


class MissingProviderKeyError(ValueError):
    """`modelscope` 后端缺少 `MAX_PROVIDER_KEY`。"""

    def __init__(self) -> None:
        """提示在 `.env` 填写魔搭 Access Token。"""
        super().__init__(
            "未设置 MAX_PROVIDER_KEY。使用 modelscope 时请在 .env 中填写魔搭 Access Token。"
        )


class ServeNotAllowedError(RuntimeError):
    """非 `local` 后端不允许启动 `max-gui serve`。"""

    def __init__(self) -> None:
        """提示把 `MAX_PROVIDER` 改回 `local`。"""
        super().__init__(
            "当前 MAX_PROVIDER 不是 local。请在 .env 中改为 local 后再运行 max-gui serve。"
        )


class MissingWeightsError(FileNotFoundError):
    """本地权重目录不完整。"""

    def __init__(self, model_name: str, path: Path) -> None:
        """参数：`model_name` 为 `MODEL_NAME`；`path` 为缺失的权重目录。"""
        self.model_name = model_name
        self.path = path
        super().__init__(f"模型权重缺失：{path}")


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


def parse_provider(raw: str | None) -> str:
    """把 `MAX_PROVIDER` 规范成 `local` 或 `modelscope`。

    参数：
        raw: 环境变量原文；空则视为 `local`。

    返回：
        后端名。

    异常：
        UnknownProviderError: 值不在允许集合中。
    """
    value = (raw or DEFAULT_PROVIDER).strip().lower()
    if value not in PROVIDERS:
        raise UnknownProviderError(raw if raw is not None else "")
    return value


def has_provider_key(api_key: str) -> bool:
    """`api_key` 是否可作为魔搭 Token（非空且不是占位 `EMPTY`）。"""
    key = api_key.strip()
    return bool(key) and key != "EMPTY"


@dataclass(slots=True)
class Settings:
    """一次运行所需的路径、推理端点与限制。

    字段由 `load_settings` 从 `.env` 与环境变量填充。
    """

    provider: str = DEFAULT_PROVIDER
    base_url: str = DEFAULT_LOCAL_BASE_URL
    api_key: str = "EMPTY"
    model_name: str = DEFAULT_LOCAL_MODEL
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
    gpu_memory_utilization: float = 0.85
    dtype: str = "auto"
    ocr_base_url: str = DEFAULT_OCR_BASE_URL
    ocr_start_timeout: float = 180.0
    ocr_timeout: float = 120.0
    ocr_gpu_memory_utilization: float = 0.20

    @property
    def model_path(self) -> Path:
        """本地权重目录：`model_root / model_name`。仅 `local` 后端使用。"""
        return self.model_root / self.model_name

    @property
    def ocr_model_path(self) -> Path:
        """PaddleOCR-VL 权重目录：`model_root / paddleocr-vl-1.5`。"""
        return self.model_root / DEFAULT_OCR_MODEL


def load_settings(
    *,
    workspace: Path | None = None,
    sessions_dir: Path | None = None,
) -> Settings:
    """从 `.env` 与环境变量组装 `Settings`。

    先按 `detect_project_root` 定位根目录并载入 `.env`（不覆盖已有环境变量）。
    环境变量：`MAX_PROVIDER`、`MAX_PROVIDER_KEY`、`MODEL_NAME`、
    `MAX_GUI_BASE_URL`、`MAX_GUI_WORKSPACE`、`MAX_GUI_MAX_ITERATIONS`、
    `MAX_GUI_MAX_IMAGE_*`、`MAX_GUI_TOOL_TIMEOUT`、`MAX_GUI_MAX_MODEL_LEN`、
    `MAX_GUI_GPU_MEM`、`MAX_GUI_DTYPE`、`MAX_GUI_OCR_*`。
    不读取 `MODELSCOPE_SDK_TOKEN`。

    参数：
        workspace: 工具读写根；缺省 `MAX_GUI_WORKSPACE` 或 cwd。
        sessions_dir: 会话 JSON 目录；缺省 `<root>/artifacts/sessions`。

    返回：
        解析后的配置。

    异常：
        UnknownProviderError: `MAX_PROVIDER` 非法。
    """
    root = detect_project_root()
    load_env_file(root)
    provider = parse_provider(os.environ.get("MAX_PROVIDER"))
    if provider == "modelscope":
        model_name = (os.environ.get("MODEL_NAME") or DEFAULT_MODELSCOPE_MODEL).strip()
        if not model_name:
            model_name = DEFAULT_MODELSCOPE_MODEL
        base_url = MODELSCOPE_BASE_URL
        api_key = (os.environ.get("MAX_PROVIDER_KEY") or "").strip()
    else:
        model_name = (os.environ.get("MODEL_NAME") or DEFAULT_LOCAL_MODEL).strip()
        if not model_name:
            model_name = DEFAULT_LOCAL_MODEL
        base_url = os.environ.get("MAX_GUI_BASE_URL") or DEFAULT_LOCAL_BASE_URL
        api_key = "EMPTY"
    settings = Settings(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        project_root=root,
        workspace=(workspace or Path(os.environ.get("MAX_GUI_WORKSPACE") or Path.cwd())).resolve(),
        sessions_dir=(sessions_dir or root / "artifacts" / "sessions").resolve(),
        screenshots_dir=(root / "artifacts" / "screenshots").resolve(),
        model_root=(root / "model").resolve(),
        max_iterations=int(os.environ.get("MAX_GUI_MAX_ITERATIONS") or 20),
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


def require_provider_key(settings: Settings) -> None:
    """`modelscope` 时必须已有 `MAX_PROVIDER_KEY`。

    异常：
        MissingProviderKeyError: 密钥为空。
    """
    if settings.provider == "modelscope" and not has_provider_key(settings.api_key):
        raise MissingProviderKeyError()


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
    """确认当前本地模型权重可用。

    返回：
        权重目录。

    异常：
        MissingWeightsError: 目录缺失或不完整。
    """
    path = settings.model_path
    if not weights_ready(path):
        raise MissingWeightsError(settings.model_name, path)
    return path
