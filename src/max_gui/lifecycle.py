"""模型生命周期：启动独立 vLLM 进程。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from max_gui.config import DEFAULT_VLLM_BIN, MissingVllmError, Settings, require_weights
from max_gui.provider import ServeNotAllowedError, get_provider


def resolve_vllm_bin(*, default: Path | None = None) -> Path:
    """定位独立的 vLLM 可执行文件，绝不回退到本项目解释器。

    查找顺序：`MAX_GUI_VLLM`、`PATH` 中的 `vllm`、`default` 或 `DEFAULT_VLLM_BIN`。

    参数：
        default: 覆盖默认候选路径，测试用。

    返回：
        可执行文件路径。

    异常：
        MissingVllmError: 环境变量无效或所有候选都不存在。
    """
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
    """阻塞启动 `vllm serve`，直到子进程退出。

    仅 `MAX_PROVIDER=local` 时允许。

    参数：
        settings: 必须已能解析到完整权重；并提供上下文长度、显存与 dtype。

    返回：
        vLLM 进程退出码。

    异常：
        ServeNotAllowedError: 当前不是 local 后端。
        MissingWeightsError: 权重目录不完整。
        MissingVllmError: 找不到 vLLM 二进制。
    """
    if not get_provider(settings.provider).allows_serve:
        raise ServeNotAllowedError()
    model_path = require_weights(settings)
    command = _serve_command(settings, model_path)
    env = os.environ.copy()
    env.setdefault("VLLM_HOST_IP", "127.0.0.1")
    env.setdefault("MASTER_ADDR", "127.0.0.1")
    env.setdefault("GLOO_SOCKET_IFNAME", "lo0")
    process = subprocess.run(command, check=False, env=env)
    return int(process.returncode)


def _serve_command(
    settings: Settings, model_path: Path, *, vllm_bin: Path | None = None
) -> list[str]:
    """拼出 `vllm serve` 参数列表。

    参数：
        settings: 提供 `--max-model-len`、显存占用、dtype 与对外模型名。
        model_path: 本地权重目录。
        vllm_bin: 指定二进制；缺省再走 `resolve_vllm_bin`。

    返回：
        可直接交给 `subprocess.run` 的命令。
    """
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
        settings.model_name,
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "qwen3_coder",
    ]
