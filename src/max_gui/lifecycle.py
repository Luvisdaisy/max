"""vLLM 二进制定位：供 OCR、OmniParser 与演示脚本复用。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from max_gui.config import DEFAULT_VLLM_BIN, MissingVllmError


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
