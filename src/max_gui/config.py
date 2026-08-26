"""运行时配置：`.env` 载入、推理后端、路径探测与权重校验。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_PROVIDER = "local"
PROVIDERS = frozenset({"local", "remote", "modelscope", "dashscope"})
CLOUD_PROVIDERS = frozenset({"modelscope", "dashscope"})
KEYED_PROVIDERS = CLOUD_PROVIDERS
DEFAULT_LOCAL_MODEL = "qwen3.5-4b"
DEFAULT_MODELSCOPE_MODEL = "Qwen/Qwen3.8-27B"
DEFAULT_DASHSCOPE_MODEL = "qwen3.8-27b"
MODELSCOPE_BASE_URL = "https://api-inference.modelscope.cn/v1"
DASHSCOPE_HOST_SUFFIX = ".cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:8000/v1"

DEFAULT_VLLM_BIN = Path.home() / ".venv-vllm-metal" / "bin" / "vllm"
DEFAULT_OCR_MODEL = "paddleocr-vl-1.5"
DEFAULT_OCR_BASE_URL = "http://127.0.0.1:8001/v1"
DEFAULT_OMNIPARSER_DIR = "omniparserv2"
DEFAULT_OMNIPARSER_BASE_URL = "http://127.0.0.1:8002"


class UnknownProviderError(ValueError):
    """`MAX_PROVIDER` 不是受支持的推理后端。"""

    def __init__(self, raw: str) -> None:
        """参数：`raw` 为用户给出的非法值。"""
        allowed = ", ".join(sorted(PROVIDERS))
        super().__init__(f"未知推理后端：{raw}。可用：{allowed}")


class MissingProviderKeyError(ValueError):
    """需要认证的云端后端缺少 `MAX_PROVIDER_KEY`。"""

    def __init__(self, provider: str = "modelscope") -> None:
        """参数：`provider` 为当前云端后端名，用于区分文案。"""
        if provider == "dashscope":
            detail = "使用 dashscope 时请在 .env 中填写百炼 API Key。"
        else:
            detail = "使用 modelscope 时请在 .env 中填写魔搭 Access Token。"
        super().__init__(f"未设置 MAX_PROVIDER_KEY。{detail}")


class MissingDashscopeWorkspaceError(ValueError):
    """`dashscope` 后端缺少 `MAX_DASHSCOPE_WORKSPACE`。"""

    def __init__(self) -> None:
        """提示在 `.env` 填写百炼业务空间 ID。"""
        super().__init__(
            "未设置 MAX_DASHSCOPE_WORKSPACE。使用 dashscope 时请在 .env 中填写百炼业务空间 ID。"
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
    """把 `MAX_PROVIDER` 规范成受支持的推理后端。

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
    """`api_key` 是否可作为云端密钥（非空且不是占位 `EMPTY`）。"""
    key = api_key.strip()
    return bool(key) and key != "EMPTY"


def has_dashscope_workspace(workspace_id: str) -> bool:
    """业务空间 ID 去空白后是否非空。"""
    return bool(workspace_id.strip())


def dashscope_base_url(workspace_id: str) -> str:
    """由业务空间 ID 拼出华北 2（北京）专属 OpenAI 兼容根路径。

    参数：
        workspace_id: 百炼业务空间 ID，调用方保证已去空白。

    返回：
        `https://{id}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。
    """
    return f"https://{workspace_id}{DASHSCOPE_HOST_SUFFIX}"


@dataclass(slots=True)
class Settings:
    """一次运行所需的路径、推理端点与限制。

    字段由 `load_settings` 从 `.env` 与环境变量填充。
    """

    provider: str = DEFAULT_PROVIDER
    base_url: str = DEFAULT_LOCAL_BASE_URL
    api_key: str = "EMPTY"
    model_name: str = DEFAULT_LOCAL_MODEL
    dashscope_workspace: str = ""
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
    omniparser_dir: str = DEFAULT_OMNIPARSER_DIR
    omniparser_base_url: str = DEFAULT_OMNIPARSER_BASE_URL
    omniparser_start_timeout: float = 180.0
    omniparser_timeout: float = 120.0

    @property
    def model_path(self) -> Path:
        """本地权重目录：`model_root / model_name`。仅 `local` 后端使用。"""
        return self.model_root / self.model_name

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
    环境变量：`MAX_PROVIDER`、`MAX_PROVIDER_KEY`、`MODEL_NAME`、
    `MAX_DASHSCOPE_WORKSPACE`、`MAX_GUI_BASE_URL`、`MAX_GUI_WORKSPACE`、
    `MAX_GUI_MAX_ITERATIONS`、`MAX_GUI_MAX_IMAGE_*`、`MAX_GUI_TOOL_TIMEOUT`、
    `MAX_GUI_MAX_MODEL_LEN`、`MAX_GUI_GPU_MEM`、`MAX_GUI_DTYPE`、`MAX_GUI_OCR_*`、
    `MAX_GUI_OMNIPARSER_*`。
    不读取 `MODELSCOPE_SDK_TOKEN` 或 `DASHSCOPE_API_KEY`。

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
    dashscope_workspace = (os.environ.get("MAX_DASHSCOPE_WORKSPACE") or "").strip()
    if provider == "modelscope":
        model_name = (os.environ.get("MODEL_NAME") or DEFAULT_MODELSCOPE_MODEL).strip()
        if not model_name:
            model_name = DEFAULT_MODELSCOPE_MODEL
        base_url = MODELSCOPE_BASE_URL
        api_key = (os.environ.get("MAX_PROVIDER_KEY") or "").strip()
    elif provider == "dashscope":
        model_name = (os.environ.get("MODEL_NAME") or DEFAULT_DASHSCOPE_MODEL).strip()
        if not model_name:
            model_name = DEFAULT_DASHSCOPE_MODEL
        base_url = dashscope_base_url(dashscope_workspace) if dashscope_workspace else ""
        api_key = (os.environ.get("MAX_PROVIDER_KEY") or "").strip()
    elif provider == "remote":
        model_name = (os.environ.get("MODEL_NAME") or DEFAULT_LOCAL_MODEL).strip()
        if not model_name:
            model_name = DEFAULT_LOCAL_MODEL
        base_url = (os.environ.get("MAX_GUI_BASE_URL") or "").strip()
        # WSL 网关仅由可信局域网与 Windows 防火墙隔离，不使用应用层 API Key。
        api_key = "EMPTY"
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
        dashscope_workspace=dashscope_workspace,
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
        omniparser_dir=(os.environ.get("MAX_GUI_OMNIPARSER_DIR") or DEFAULT_OMNIPARSER_DIR).strip(),
        omniparser_base_url=os.environ.get("MAX_GUI_OMNIPARSER_BASE_URL")
        or DEFAULT_OMNIPARSER_BASE_URL,
        omniparser_start_timeout=float(os.environ.get("MAX_GUI_OMNIPARSER_START_TIMEOUT") or 180),
        omniparser_timeout=float(os.environ.get("MAX_GUI_OMNIPARSER_TIMEOUT") or 120),
    )
    return settings


def require_provider_key(settings: Settings) -> None:
    """需要认证的云端后端必须已有 `MAX_PROVIDER_KEY`。

    异常：
        MissingProviderKeyError: 密钥为空。
    """
    if settings.provider in KEYED_PROVIDERS and not has_provider_key(settings.api_key):
        raise MissingProviderKeyError(settings.provider)


def require_dashscope_workspace(settings: Settings) -> None:
    """`dashscope` 时必须已有 `MAX_DASHSCOPE_WORKSPACE`。

    异常：
        MissingDashscopeWorkspaceError: 业务空间 ID 为空。
    """
    if settings.provider == "dashscope" and not has_dashscope_workspace(
        settings.dashscope_workspace
    ):
        raise MissingDashscopeWorkspaceError()


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
