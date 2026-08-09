from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

from .artifacts import ExperimentArchive


def _safe_error(error: Exception) -> str:
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
    """Run one locally-loaded inference and persist a complete result record."""
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
