from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL_ALIAS = "qwen3.5-2b"

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
    pass


class MissingWeightsError(FileNotFoundError):
    def __init__(self, alias: str, download_cmd: str) -> None:
        self.alias = alias
        self.download_cmd = download_cmd
        super().__init__(f"模型权重缺失：{alias}。请先运行：{download_cmd}")


DEFAULT_VLLM_BIN = Path.home() / ".venv-vllm-metal" / "bin" / "vllm"


class MissingVllmError(FileNotFoundError):
    def __init__(self) -> None:
        super().__init__(
            "找不到 vLLM 可执行文件。请先 `source ~/.venv-vllm-metal/bin/activate`，"
            "或设置 MAX_GUI_VLLM 指向 vllm 二进制"
            f"（默认路径：{DEFAULT_VLLM_BIN}）。"
        )


def detect_project_root() -> Path:
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
    key = raw.strip().lower()
    if key not in MODEL_ALIASES:
        known = ", ".join(sorted(set(MODEL_ALIASES.values())))
        raise UnknownModelError(f"未知模型别名：{raw}。可用：{known}")
    return MODEL_ALIASES[key]


def download_command(alias: str) -> str:
    canonical = resolve_model_alias(alias)
    return f"max-gui download {canonical}"


@dataclass(slots=True)
class Settings:
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

    @property
    def canonical_model(self) -> str:
        return resolve_model_alias(self.model_alias)

    @property
    def model_path(self) -> Path:
        return self.model_root / self.canonical_model

    def with_model(self, alias: str) -> Settings:
        canonical = resolve_model_alias(alias)
        return Settings(
            base_url=self.base_url,
            api_key=self.api_key,
            model_alias=canonical,
            project_root=self.project_root,
            workspace=self.workspace,
            sessions_dir=self.sessions_dir,
            screenshots_dir=self.screenshots_dir,
            model_root=self.model_root,
            max_iterations=self.max_iterations,
            max_image_edge=self.max_image_edge,
            max_image_bytes=self.max_image_bytes,
            tool_timeout=self.tool_timeout,
            max_model_len=self.max_model_len,
            gpu_memory_utilization=self.gpu_memory_utilization,
            dtype=self.dtype,
        )


def load_settings(
    *,
    workspace: Path | None = None,
    model: str | None = None,
    sessions_dir: Path | None = None,
    base_url: str | None = None,
) -> Settings:
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
    )
    return settings


def weights_ready(path: Path) -> bool:
    if not path.is_dir():
        return False
    weights = list(path.glob("*.safetensors")) + list(path.glob("*.bin"))
    if not weights:
        return False
    return not any(
        p.suffix == ".incomplete" or p.name.endswith(".incomplete") for p in path.iterdir()
    )


def require_weights(settings: Settings) -> Path:
    path = settings.model_path
    if not weights_ready(path):
        raise MissingWeightsError(
            settings.canonical_model, download_command(settings.canonical_model)
        )
    return path
