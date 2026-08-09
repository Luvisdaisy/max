from __future__ import annotations

import importlib.metadata
import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class DiagnosticProbe:
    python_version: Callable[[], str]
    package_versions: Callable[[], dict[str, str]]
    cuda_available: Callable[[], bool]
    cuda_version: Callable[[], str | None]
    bf16_probe: Callable[[], None]
    dependency_check: Callable[[], list[str]]
    gpu_name: Callable[[], str | None] = lambda: None
    tool_checks: Callable[[], list[CheckResult]] = lambda: []


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    python_version: str
    packages: dict[str, str]
    cuda_available: bool
    cuda_version: str | None
    bf16_supported: bool
    failures: list[str]
    gpu_name: str | None = None
    tool_checks: list[CheckResult] | None = None

    @property
    def ok(self) -> bool:
        return not self.failures and not any(
            check.status == "failed" for check in self.tool_checks or []
        )

    @property
    def checks(self) -> list[CheckResult]:
        checks = [
            CheckResult("python", "passed", self.python_version.split()[0]),
            CheckResult(
                "dependencies",
                "passed"
                if not any("dependency" in failure.lower() for failure in self.failures)
                else "failed",
                "pip check",
            ),
            CheckResult(
                "cuda",
                "passed" if self.cuda_available else "failed",
                self.cuda_version or "unavailable",
            ),
            CheckResult(
                "bf16",
                "passed" if self.bf16_supported else "failed",
                "CUDA BF16 tensor operation",
            ),
        ]
        if self.gpu_name:
            checks.append(CheckResult("gpu", "passed", self.gpu_name))
        return checks + (self.tool_checks or [])

    def to_dict(self) -> dict[str, object]:
        return {
            "python_version": self.python_version,
            "platform": platform.platform(),
            "packages": self.packages,
            "cuda_available": self.cuda_available,
            "cuda_version": self.cuda_version,
            "bf16_supported": self.bf16_supported,
            "failures": self.failures,
            "checks": [check.to_dict() for check in self.checks],
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
        except (
            Exception
        ) as error:  # diagnostic boundary: capture library errors as evidence
            failures.append(f"BF16 CUDA tensor operation failed: {error}")
    failures.extend(probe.dependency_check())
    try:
        tool_checks = probe.tool_checks()
    except (
        Exception
    ) as error:  # diagnostic boundary: capture base-tool probe failures as evidence
        tool_checks = [
            CheckResult("base_tools", "failed", f"Base-tool probe failed: {error}")
        ]
    return DiagnosticResult(
        python_version=probe.python_version(),
        packages=probe.package_versions(),
        cuda_available=cuda_available,
        cuda_version=cuda_version,
        bf16_supported=bf16_supported,
        failures=failures,
        gpu_name=probe.gpu_name() if cuda_available else None,
        tool_checks=tool_checks,
    )


def default_probe(*, desktop_probe: bool = False) -> DiagnosticProbe:
    def package_versions() -> dict[str, str]:
        names = (
            "torch",
            "torchvision",
            "transformers",
            "modelscope",
            "langchain",
            "langgraph",
        )
        return {
            name: importlib.metadata.version(name)
            for name in names
            if _is_installed(name)
        }

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
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "check"],
            capture_output=True,
            text=True,
            check=False,
        )
        return (
            []
            if completed.returncode == 0
            else [completed.stdout.strip() or completed.stderr.strip()]
        )

    def tool_checks() -> list[CheckResult]:
        checks = [
            _check_mss(),
            _check_pyautogui(),
            _check_opencv(),
            _check_paddleocr(),
            _check_pynput(),
        ]
        checks.append(
            _check_desktop_probe()
            if desktop_probe
            else CheckResult(
                "desktop_probe",
                "skipped",
                "Use --desktop-probe in an interactive session.",
            )
        )
        return checks

    return DiagnosticProbe(
        python_version=lambda: sys.version,
        package_versions=package_versions,
        cuda_available=cuda_available,
        cuda_version=cuda_version,
        bf16_probe=bf16_probe,
        dependency_check=dependency_check,
        gpu_name=lambda: __import__("torch").cuda.get_device_name(0),
        tool_checks=tool_checks,
    )


def render_doctor(result: DiagnosticResult) -> str:
    groups = {"passed": "通过", "failed": "失败", "skipped": "跳过"}
    lines = ["Doctor 结果：" + ("通过" if result.ok else "失败")]
    for status, label in groups.items():
        checks = [check for check in result.checks if check.status == status]
        if checks:
            lines.append(f"{label}：")
            lines.extend(f"- {check.name}: {check.detail}" for check in checks)
    if result.failures:
        lines.append("错误：")
        lines.extend(f"- {failure}" for failure in result.failures)
    return "\n".join(lines)


def _check(name: str, probe: Callable[[], str]) -> CheckResult:
    try:
        return CheckResult(name, "passed", probe())
    except Exception as error:  # diagnostic boundary: third-party GUI tooling may be unavailable headlessly
        return CheckResult(name, "failed", f"{type(error).__name__}: {error}")


def _check_mss() -> CheckResult:
    def probe() -> str:
        import mss

        with mss.mss() as capture:
            image = capture.grab(capture.monitors[0])
        return f"in-memory screenshot {image.width}x{image.height}"

    return _check("mss", probe)


def _check_pyautogui() -> CheckResult:
    def probe() -> str:
        import pyautogui

        size = pyautogui.size()
        return f"screen {size.width}x{size.height}"

    return _check("pyautogui", probe)


def _check_opencv() -> CheckResult:
    def probe() -> str:
        import cv2
        import numpy

        converted = cv2.cvtColor(
            numpy.zeros((1, 1, 3), dtype=numpy.uint8), cv2.COLOR_BGR2GRAY
        )
        return f"synthetic image converted to {converted.shape[1]}x{converted.shape[0]}"

    return _check("opencv", probe)


def _check_paddleocr() -> CheckResult:
    return _check(
        "paddleocr",
        lambda: f"version {importlib.metadata.version('paddleocr')} available",
    )


def _check_pynput() -> CheckResult:
    def probe() -> str:
        import pynput

        return f"module {pynput.__name__} available"

    return _check("pynput", probe)


def _check_desktop_probe() -> CheckResult:
    root = None
    try:
        import ctypes
        import tkinter

        import pyautogui

        root = tkinter.Tk()
        root.title("MAX Doctor Desktop Probe")
        root.geometry("360x140+40+40")
        received = tkinter.StringVar()
        clicked = tkinter.BooleanVar(value=False)
        entry = tkinter.Entry(root, textvariable=received)
        entry.place(x=20, y=20, width=320, height=28)
        button = tkinter.Button(root, text="Confirm", command=lambda: clicked.set(True))
        button.place(x=20, y=65, width=120, height=32)
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
        root.update_idletasks()
        root.update()
        window_handle = root.winfo_id()
        request_foreground_window(
            window_handle, ctypes.windll.user32.SetForegroundWindow
        )
        root.update()
        if not is_foreground_window(
            window_handle, ctypes.windll.user32.GetForegroundWindow
        ):
            return CheckResult(
                "desktop_probe", "skipped", foreground_probe_skip_detail()
            )

        def center(widget: object) -> tuple[int, int]:
            return (
                widget.winfo_rootx() + widget.winfo_width() // 2,
                widget.winfo_rooty() + widget.winfo_height() // 2,
            )

        entry_point = center(entry)
        if root.winfo_containing(*entry_point) is not entry:
            raise RuntimeError("controlled input field is unavailable")
        pyautogui.click(*entry_point)
        pyautogui.write("doctor")
        root.update()
        button_point = center(button)
        if root.winfo_containing(*button_point) is not button:
            raise RuntimeError("controlled confirmation button is unavailable")
        pyautogui.click(*button_point)
        root.update()
        if received.get() != "doctor" or not clicked.get():
            raise RuntimeError(
                "controlled desktop input did not reach the probe window"
            )
        return CheckResult(
            "desktop_probe", "passed", "controlled click and text input verified"
        )
    except Exception as error:  # desktop probe is explicitly opt-in and must never propagate input on setup failure
        return CheckResult(
            "desktop_probe", "failed", f"{type(error).__name__}: {error}"
        )
    finally:
        if root is not None:
            root.destroy()


def is_foreground_window(
    window_handle: int, get_foreground_window: Callable[[], int]
) -> bool:
    return window_handle == get_foreground_window()


def request_foreground_window(
    window_handle: int, set_foreground_window: Callable[[int], object]
) -> None:
    set_foreground_window(window_handle)


def foreground_probe_skip_detail() -> str:
    return "temporary probe window could not obtain Windows foreground focus; no desktop input was sent. Bring the interactive Windows session to the foreground and rerun --desktop-probe."


def _is_installed(package: str) -> bool:
    try:
        importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True
