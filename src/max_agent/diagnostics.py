"""采集本地依赖、CUDA 与桌面能力诊断，并避免诊断过程产生控制行为。"""

from __future__ import annotations

import ctypes
import importlib.metadata
import platform
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class _INPUT_VALUE(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("value", _INPUT_VALUE)]


@dataclass(frozen=True, slots=True)
class CheckResult:
    """单项诊断的名称、状态与可显示详情。"""

    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class DiagnosticProbe:
    """可替换的诊断依赖集合，使平台探测可在测试中隔离。"""

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
    """诊断汇总及其符合性判断，用于 CLI 渲染和证据归档。"""

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
    """按稳定顺序运行环境探针，保证同类诊断结果可比较。"""
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
    """构造默认探针；桌面探测仅在用户显式请求时启用。"""

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
    import json

    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "from max_agent.diagnostics import _desktop_probe_worker_main; _desktop_probe_worker_main()",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CheckResult("desktop_probe", "failed", "desktop probe worker timed out")
    if completed.returncode:
        status = completed.returncode & 0xFFFFFFFF
        return CheckResult(
            "desktop_probe",
            "failed",
            f"desktop probe worker exited with status 0x{status:08X}",
        )
    try:
        payload = json.loads(completed.stdout)
        return CheckResult(**payload)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        return CheckResult(
            "desktop_probe",
            "failed",
            f"desktop probe worker returned an invalid result: {type(error).__name__}",
        )


def _desktop_probe_worker_main() -> None:
    import json

    result = _run_desktop_probe()
    print(
        json.dumps(
            {"name": result.name, "status": result.status, "detail": result.detail}
        )
    )


def _run_desktop_probe() -> CheckResult:
    """在独立子进程中使用 Win32 原生控件验证受控桌面输入。"""
    user32 = None
    window_handle = 0
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        configure_win32_probe_api(user32, kernel32)
        enable_per_monitor_dpi_awareness(user32.SetProcessDpiAwarenessContext)
        instance = kernel32.GetModuleHandleW(None)
        window_handle = int(
            user32.CreateWindowExW(
                0,
                "STATIC",
                "MAX Doctor Desktop Probe",
                0x10CF0000,
                40,
                40,
                360,
                160,
                None,
                None,
                instance,
                None,
            )
            or 0
        )
        if not window_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        edit_handle = int(
            user32.CreateWindowExW(
                0x200,
                "EDIT",
                "",
                0x50810080,
                20,
                20,
                320,
                28,
                window_handle,
                1001,
                instance,
                None,
            )
            or 0
        )
        button_handle = int(
            user32.CreateWindowExW(
                0,
                "BUTTON",
                "Confirm",
                0x50010003,
                20,
                65,
                120,
                32,
                window_handle,
                1002,
                instance,
                None,
            )
            or 0
        )
        if not edit_handle or not button_handle:
            raise ctypes.WinError(ctypes.get_last_error())
        user32.ShowWindow(window_handle, 5)
        user32.UpdateWindow(window_handle)
        pump_events = lambda: pump_win32_messages(user32)
        request_controlled_foreground_window(
            window_handle, user32, kernel32.GetCurrentThreadId
        )
        if not wait_for_foreground_window(
            window_handle, user32.GetForegroundWindow, pump_events
        ):
            return CheckResult(
                "desktop_probe", "skipped", foreground_probe_skip_detail()
            )

        entry_point = win32_window_center(edit_handle, user32)
        if win32_window_at(entry_point, user32) != edit_handle:
            raise RuntimeError("controlled input field is unavailable")
        send_controlled_click(entry_point, user32)
        if not wait_for_probe_condition(
            lambda: int(user32.GetFocus() or 0) == edit_handle, pump_events
        ):
            raise RuntimeError("controlled input field could not receive focus")
        if not is_foreground_window(window_handle, user32.GetForegroundWindow):
            raise RuntimeError(
                "probe window lost foreground focus before controlled text input"
            )
        send_controlled_text("doctor", user32)
        if not wait_for_probe_condition(
            lambda: win32_window_text(edit_handle, user32) == "doctor", pump_events
        ):
            raise RuntimeError("controlled text input did not reach the probe window")

        button_point = win32_window_center(button_handle, user32)
        if win32_window_at(button_point, user32) != button_handle:
            raise RuntimeError("controlled confirmation button is unavailable")
        if not is_foreground_window(window_handle, user32.GetForegroundWindow):
            raise RuntimeError(
                "probe window lost foreground focus before controlled click"
            )
        send_controlled_click(button_point, user32)
        if not wait_for_probe_condition(
            lambda: user32.SendMessageW(button_handle, 0x00F0, 0, 0) == 1,
            pump_events,
        ):
            raise RuntimeError("controlled click did not reach the probe window")
        return CheckResult(
            "desktop_probe",
            "passed",
            "Win32 controlled click and text input verified",
        )
    except Exception as error:  # desktop probe is explicitly opt-in and must never propagate input on setup failure
        return CheckResult(
            "desktop_probe", "failed", f"{type(error).__name__}: {error}"
        )
    finally:
        if window_handle and user32 is not None:
            user32.DestroyWindow(window_handle)


def is_foreground_window(
    window_handle: int, get_foreground_window: Callable[[], int]
) -> bool:
    return window_handle == get_foreground_window()


def configure_win32_probe_api(user32: object, kernel32: object) -> None:
    user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        wintypes.LPVOID,
    ]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.UpdateWindow.argtypes = [wintypes.HWND]
    user32.UpdateWindow.restype = wintypes.BOOL
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetFocus.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, wintypes.LPVOID]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.BOOL,
    ]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.BringWindowToTop.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [
        wintypes.HWND,
        wintypes.LPWSTR,
        ctypes.c_int,
    ]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.TranslateMessage.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    user32.DispatchMessageW.restype = ctypes.c_ssize_t
    user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetCursorPos.restype = wintypes.BOOL
    user32.SendInput.argtypes = [
        wintypes.UINT,
        ctypes.POINTER(_INPUT),
        ctypes.c_int,
    ]
    user32.SendInput.restype = wintypes.UINT
    user32.SendMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HINSTANCE
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD


def pump_win32_messages(user32: object) -> None:
    message = wintypes.MSG()
    while user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
        user32.TranslateMessage(ctypes.byref(message))
        user32.DispatchMessageW(ctypes.byref(message))


def win32_window_center(window_handle: int, user32: object) -> tuple[int, int]:
    rectangle = wintypes.RECT()
    if not user32.GetWindowRect(window_handle, ctypes.byref(rectangle)):
        raise ctypes.WinError(ctypes.get_last_error())
    return (
        (rectangle.left + rectangle.right) // 2,
        (rectangle.top + rectangle.bottom) // 2,
    )


def win32_window_at(point: tuple[int, int], user32: object) -> int:
    return int(user32.WindowFromPoint(wintypes.POINT(*point)) or 0)


def win32_window_text(window_handle: int, user32: object) -> str:
    length = user32.GetWindowTextLengthW(window_handle)
    buffer = ctypes.create_unicode_buffer(length + 1)
    if not user32.GetWindowTextW(window_handle, buffer, len(buffer)) and length:
        raise ctypes.WinError(ctypes.get_last_error())
    return buffer.value


def enable_per_monitor_dpi_awareness(
    set_process_dpi_awareness_context: Callable[[int], object],
) -> None:
    set_process_dpi_awareness_context(-4)


def send_controlled_text(text: str, user32: object) -> None:
    encoded = text.encode("utf-16-le")
    units = [
        int.from_bytes(encoded[index : index + 2], "little")
        for index in range(0, len(encoded), 2)
    ]
    events: list[_INPUT] = []
    for unit in units:
        events.extend(
            [
                _INPUT(
                    type=1,
                    value=_INPUT_VALUE(ki=_KEYBDINPUT(wScan=unit, dwFlags=0x0004)),
                ),
                _INPUT(
                    type=1,
                    value=_INPUT_VALUE(ki=_KEYBDINPUT(wScan=unit, dwFlags=0x0006)),
                ),
            ]
        )
    send_input_checked(events, user32)


def send_controlled_click(point: tuple[int, int], user32: object) -> None:
    ctypes.set_last_error(0)
    if not user32.SetCursorPos(*point):
        raise ctypes.WinError(ctypes.get_last_error())
    send_input_checked(
        [
            _INPUT(
                type=0,
                value=_INPUT_VALUE(mi=_MOUSEINPUT(dwFlags=0x0002)),
            ),
            _INPUT(
                type=0,
                value=_INPUT_VALUE(mi=_MOUSEINPUT(dwFlags=0x0004)),
            ),
        ],
        user32,
    )


def send_input_checked(events: list[_INPUT], user32: object) -> None:
    if not events:
        return
    event_array = (_INPUT * len(events))(*events)
    ctypes.set_last_error(0)
    inserted = user32.SendInput(len(events), event_array, ctypes.sizeof(_INPUT))
    if inserted != len(events):
        error_code = ctypes.get_last_error()
        raise RuntimeError(
            f"SendInput inserted {inserted} of {len(events)} events "
            f"(GetLastError={error_code})"
        )


def wait_for_probe_condition(
    condition: Callable[[], bool],
    pump_events: Callable[[], None],
    timeout_s: float = 1.0,
    time_fn: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    deadline = time_fn() + timeout_s
    while True:
        pump_events()
        if condition():
            return True
        if time_fn() >= deadline:
            return False
        sleep(0.01)


def wait_for_foreground_window(
    window_handle: int,
    get_foreground_window: Callable[[], int],
    pump_events: Callable[[], None],
    timeout_s: float = 3.0,
    time_fn: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> bool:
    deadline = time_fn() + timeout_s
    while True:
        pump_events()
        if is_foreground_window(window_handle, get_foreground_window):
            return True
        if time_fn() >= deadline:
            return False
        sleep(0.05)


def request_foreground_window(
    window_handle: int, set_foreground_window: Callable[[int], object]
) -> None:
    set_foreground_window(window_handle)


def request_controlled_foreground_window(
    window_handle: int,
    user32: object,
    get_current_thread_id: Callable[[], int] | None = None,
) -> None:
    if get_current_thread_id is None:
        import ctypes

        get_current_thread_id = ctypes.windll.kernel32.GetCurrentThreadId
    foreground_handle = user32.GetForegroundWindow()
    current_thread = get_current_thread_id()
    foreground_thread = (
        user32.GetWindowThreadProcessId(foreground_handle, None)
        if foreground_handle
        else current_thread
    )
    attached = foreground_thread != current_thread and bool(
        user32.AttachThreadInput(current_thread, foreground_thread, True)
    )
    try:
        user32.BringWindowToTop(window_handle)
        user32.SetForegroundWindow(window_handle)
    finally:
        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)


def foreground_probe_skip_detail() -> str:
    return "temporary probe window could not obtain Windows foreground focus within 3 seconds; no desktop input was sent. In an interactive Windows session, use Alt+Tab to focus the temporary window and rerun --desktop-probe."


def _is_installed(package: str) -> bool:
    try:
        importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True
