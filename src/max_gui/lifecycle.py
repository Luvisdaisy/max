from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from max_gui.config import (
    DEFAULT_VLLM_BIN,
    MODELSCOPE_IDS,
    MissingVllmError,
    Settings,
    require_weights,
    resolve_model_alias,
)


def download_model(settings: Settings, alias: str | None = None) -> Path:
    canonical = resolve_model_alias(alias or settings.model_alias)
    dest = settings.model_root / canonical
    dest.mkdir(parents=True, exist_ok=True)
    model_id = MODELSCOPE_IDS[canonical]
    from modelscope.hub.snapshot_download import snapshot_download

    snapshot_download(model_id, local_dir=str(dest))
    return dest


def resolve_vllm_bin(*, default: Path | None = None) -> Path:
    """Locate the standalone vLLM CLI. Never fall back to the project interpreter."""
    env = os.environ.get("MAX_GUI_VLLM")
    if env:
        path = Path(env).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise MissingVllmError()

    found = shutil.which("vllm")
    if found:
        return Path(found)

    candidate = default if default is not None else DEFAULT_VLLM_BIN
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    raise MissingVllmError()


def serve_model(settings: Settings) -> int:
    model_path = require_weights(settings)
    command = _serve_command(settings, model_path)
    env = os.environ.copy()
    env.setdefault("VLLM_HOST_IP", "127.0.0.1")
    env.setdefault("MASTER_ADDR", "127.0.0.1")
    env.setdefault("GLOO_SOCKET_IFNAME", "lo0")
    process = subprocess.run(command, check=False, env=env)
    return int(process.returncode)


def _serve_command(settings: Settings, model_path: Path, *, vllm_bin: Path | None = None) -> list[str]:
    binary = vllm_bin or resolve_vllm_bin()
    return [
        str(binary),
        "serve",
        str(model_path),
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
        "--max-model-len",
        str(settings.max_model_len),
        "--gpu-memory-utilization",
        str(settings.gpu_memory_utilization),
        "--dtype",
        settings.dtype,
        "--served-model-name",
        settings.canonical_model,
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "qwen3_coder",
    ]
