"""隔离 Chrome 与只读 URL 观察器。

Chrome 仅以临时 profile 和回环调试端口启动。URL 观察器不是 Agent 工具，不读取 DOM、不执行脚本，且拒绝
任何非回环地址。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


class IsolatedChrome:
    """一次评测批次专用的 Chrome 进程和临时 profile。"""

    def __init__(self, port: int, chrome_path: str | None = None) -> None:
        """保存仅回环端口；实际 profile 在 `start` 时创建。"""
        if not 1024 <= port <= 65535:
            raise ValueError("Chrome 调试端口必须介于 1024 和 65535")
        self.port = port
        self.chrome_path = chrome_path
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self.process: subprocess.Popen[bytes] | None = None

    def command(self, website: str, profile: Path) -> list[str]:
        """构造固定、隔离且仅回环的 Chrome 启动命令。

        参数：`website` 必须为任务起始 URL，`profile` 是本次临时资料目录。
        返回：不含 shell 拼接的参数数组。
        """
        executable = self.chrome_path or _find_chrome()
        return [
            executable,
            f"--user-data-dir={profile}",
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={self.port}",
            "--window-size=1440,1000",
            "--force-device-scale-factor=1",
            "--lang=en-US",
            "--no-first-run",
            "--no-default-browser-check",
            website,
        ]

    def start(
        self, website: str, popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen
    ) -> None:
        """创建临时 profile 后启动专用 Chrome。

        异常：找不到浏览器或进程启动失败时向调用方抛出，由编排器归类为环境错误。
        """
        if self.process is not None:
            raise RuntimeError("隔离 Chrome 已启动")
        self._temporary = tempfile.TemporaryDirectory(prefix="max-gui-mind2web-")
        profile = Path(self._temporary.name)
        self.process = popen(
            self.command(website, profile), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def close(self) -> None:
        """停止专用进程并删除本次临时 profile，不触及用户默认资料。"""
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        if self._temporary is not None:
            self._temporary.cleanup()
            self._temporary = None

    def __enter__(self) -> IsolatedChrome:
        """允许以 context manager 管理临时浏览器。"""
        return self

    def __exit__(self, *_: object) -> None:
        """退出上下文时保证清理进程与 profile。"""
        self.close()


class UrlObserver:
    """只从专用 Chrome 调试端点读取当前 tab URL。"""

    def __init__(self, port: int, fetch: Callable[[str], bytes] | None = None) -> None:
        """注入可测试的只读 JSON 获取器。"""
        self.port = port
        self.fetch = fetch or _fetch

    def current_url(self) -> str | None:
        """返回当前页面 HTTP(S) URL；无法观察时返回 `None`，绝不降级读取 DOM。"""
        endpoint = f"http://127.0.0.1:{self.port}/json"
        raw = self.fetch(endpoint)
        items = json.loads(raw.decode("utf-8"))
        if not isinstance(items, list):
            raise RuntimeError("Chrome 调试端点返回了非列表数据")
        for item in items:
            if isinstance(item, dict) and item.get("type") == "page":
                value = str(item.get("url") or "")
                parsed = urlparse(value)
                if parsed.scheme in {"http", "https"} and parsed.hostname:
                    return value
        return None


def _find_chrome() -> str:
    """定位 macOS 或 PATH 中的 Chrome 可执行文件。"""
    mac_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(mac_path).is_file():
        return mac_path
    found = shutil.which("google-chrome") or shutil.which("chromium")
    if found:
        return found
    raise FileNotFoundError("未找到 Google Chrome；请通过 --chrome-path 显式指定")


def _fetch(endpoint: str) -> bytes:
    """以短超时只读获取回环 JSON。"""
    if urlparse(endpoint).hostname != "127.0.0.1":
        raise ValueError("URL 观察器只允许访问回环调试端点")
    with urlopen(endpoint, timeout=2) as response:
        return response.read()
