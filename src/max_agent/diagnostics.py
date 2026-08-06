from __future__ import annotations

import importlib.metadata
import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class DiagnosticProbe:
    python_version: Callable[[], str]
    package_versions: Callable[[], dict[str, str]]
    cuda_available: Callable[[], bool]
    cuda_version: Callable[[], str | None]
    bf16_probe: Callable[[], None]
    dependency_check: Callable[[], list[str]]


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    python_version: str
    packages: dict[str, str]
    cuda_available: bool
    cuda_version: str | None
    bf16_supported: bool
    failures: list[str]

    @property
    def ok(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, object]:
        return {
            "python_version": self.python_version,
            "platform": platform.platform(),
            "packages": self.packages,
            "cuda_available": self.cuda_available,
            "cuda_version": self.cuda_version,
            "bf16_supported": self.bf16_supported,
            "failures": self.failures,
            "ok": self.ok,
        }


def run_diagnostics(probe: DiagnosticProbe) -> DiagnosticResult:
    failures: list[str] = []
    cuda_available = probe.cuda_available()
    cuda_version = probe.cuda_version()
    bf16_supported = False
    if not cuda_available:
        failures.append("CUDA is not available")
    else:
        try:
            probe.bf16_probe()
            bf16_supported = True
        except Exception as error:  # diagnostic boundary: capture library errors as evidence
            failures.append(f"BF16 CUDA tensor operation failed: {error}")
    failures.extend(probe.dependency_check())
    return DiagnosticResult(
        python_version=probe.python_version(),
        packages=probe.package_versions(),
        cuda_available=cuda_available,
        cuda_version=cuda_version,
        bf16_supported=bf16_supported,
        failures=failures,
    )


def default_probe() -> DiagnosticProbe:
    def package_versions() -> dict[str, str]:
        names = ("torch", "torchvision", "transformers", "modelscope", "langchain", "langgraph")
        return {name: importlib.metadata.version(name) for name in names if _is_installed(name)}

    def cuda_available() -> bool:
        import torch

        return bool(torch.cuda.is_available())

    def cuda_version() -> str | None:
        import torch

        return torch.version.cuda

    def bf16_probe() -> None:
        import torch

        tensor = torch.ones((8, 8), device="cuda", dtype=torch.bfloat16)
        _ = tensor @ tensor
        torch.cuda.synchronize()

    def dependency_check() -> list[str]:
        completed = subprocess.run([sys.executable, "-m", "pip", "check"], capture_output=True, text=True, check=False)
        return [] if completed.returncode == 0 else [completed.stdout.strip() or completed.stderr.strip()]

    return DiagnosticProbe(
        python_version=lambda: sys.version,
        package_versions=package_versions,
        cuda_available=cuda_available,
        cuda_version=cuda_version,
        bf16_probe=bf16_probe,
        dependency_check=dependency_check,
    )


def _is_installed(package: str) -> bool:
    try:
        importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True
