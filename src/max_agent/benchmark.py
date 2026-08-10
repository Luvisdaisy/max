"""执行离线模型基准并归档每个阶段的可复核结果。"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

from .artifacts import ExperimentArchive


def _safe_error(error: Exception) -> str:
    """脱敏异常消息中的绝对路径，避免证据文件泄露本机目录。"""
    return re.sub(r"(?:[A-Za-z]:[\\/]|/)[^\s\"']+", "<path>", str(error))


def run_benchmark(
    *,
    archive: ExperimentArchive,
    config: Mapping[str, Any],
    environment: Mapping[str, Any],
    load_model: Callable[[], object],
    infer: Callable[[object], Mapping[str, Any]],
    peak_memory_bytes: Callable[[], int],
    preflight: Callable[[], None] = lambda: None,
) -> dict[str, Any]:
    """运行一次本地推理，并无论成功失败均保存完整阶段记录。"""
    archive.write_config(dict(config))
    archive.write_environment(dict(environment))
    archive.append_trajectory({"event": "benchmark_started"})
    stage = "preflight"
    try:
        preflight()
        archive.append_trajectory({"event": "benchmark_preflight_passed"})
        stage = "load"
        load_started = perf_counter()
        model = load_model()
        load_seconds = perf_counter() - load_started
        stage = "inference"
        inference_started = perf_counter()
        output = dict(infer(model))
        inference_seconds = perf_counter() - inference_started
        result = {
            "status": "success",
            "stage": "completed",
            "offline": bool(config.get("offline", True)),
            "load_seconds": load_seconds,
            "inference_seconds": inference_seconds,
            "peak_gpu_memory_bytes": peak_memory_bytes(),
            "output": output,
        }
        archive.append_trajectory({"event": "benchmark_completed"})
        archive.write_result(result)
        return result
    except Exception as error:
        # 基准失败同样需要持久化阶段和脱敏原因，才能定位环境或模型问题。
        safe_error = _safe_error(error)
        result = {
            "status": "failure",
            "stage": stage,
            "offline": bool(config.get("offline", True)),
            "error": safe_error,
        }
        archive.append_trajectory(
            {"event": "benchmark_failed", "stage": stage, "error": safe_error}
        )
        archive.write_result(result)
        raise
