"""交互 Agent 专属的受控 Chrome 生命周期管理。

与 Mind2Web 评测浏览器完全分离：本会话创建临时 profile，调试接口仅绑定回环，并由
`max-gui` 在关闭时终止进程和清理目录。
"""

from __future__ import annotations

import socket
import subprocess
import tempfile
from pathlib import Path


class ControlledChromeSession:
    """交互运行期间唯一拥有的受控 Chrome 进程。"""

    def __init__(self, *, chrome_path: str | None = None) -> None:
        """参数：可选 Chrome 可执行文件路径；未给出时按本机默认位置查找。"""
        self.chrome_path = chrome_path
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.port: int | None = None

    @property
    def endpoint(self) -> str | None:
        """返回当前回环 CDP 地址；未启动时返回空。"""
        return f"http://127.0.0.1:{self.port}" if self.port else None

    def start(self, url: str = "about:blank") -> str:
        """启动临时 profile Chrome 并返回仅回环的 CDP 地址。"""
        if self.process is not None:
            raise RuntimeError("交互 Chrome 已启动")
        self._temporary = tempfile.TemporaryDirectory(prefix="max-gui-interactive-")
        try:
            self.port = _free_loopback_port()
            executable = self.chrome_path or _find_chrome()
            self.process = subprocess.Popen(
                [
                    executable,
                    f"--user-data-dir={self._temporary.name}",
                    "--remote-debugging-address=127.0.0.1",
                    f"--remote-debugging-port={self.port}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    url,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, RuntimeError) as exc:
            self.close()
            raise RuntimeError(f"无法启动受控 Chrome：{exc}") from exc
        return self.endpoint or ""

    def close(self) -> None:
        """停止受控 Chrome 并删除专属临时 profile，不触及用户浏览器数据。"""
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        self.port = None
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None


def _free_loopback_port() -> int:
    """向系统申请一个临时回环端口；socket 立即关闭以供 Chrome 绑定。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _find_chrome() -> str:
    """查找本机 Chrome 可执行文件，不导入或复用 Mind2Web 的评测实现。"""
    candidates = (
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("未找到 Google Chrome，无法启动受控浏览器会话")
