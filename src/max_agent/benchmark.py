from __future__ import annotations

from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

from .artifacts import ExperimentArchive


def run_benchmark(
    *,
    archive: ExperimentArchive,
    config: Mapping[str, Any],
    environment: Mapping[str, Any],
    load_model: Callable[[], object],
    infer: Callable[[object], Mapping[str, Any]],
    peak_memory_bytes: Callable[[], int],
) -> dict[str, Any]:
    """Run one locally-loaded inference and persist a complete result record."""
    archive.write_config(dict(config))
    archive.write_environment(dict(environment))
    archive.append_trajectory({"event": "benchmark_started"})
    load_started = perf_counter()
    try:
        model = load_model()
        load_seconds = perf_counter() - load_started
        inference_started = perf_counter()
        output = dict(infer(model))
        inference_seconds = perf_counter() - inference_started
        result = {
            "status": "success",
            "load_seconds": load_seconds,
            "inference_seconds": inference_seconds,
            "peak_gpu_memory_bytes": peak_memory_bytes(),
            "output": output,
        }
        archive.append_trajectory({"event": "benchmark_completed"})
        archive.write_result(result)
        return result
    except Exception as error:
        result = {"status": "failure", "error": str(error)}
        archive.append_trajectory({"event": "benchmark_failed", "error": str(error)})
        archive.write_result(result)
        raise
