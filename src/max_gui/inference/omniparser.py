"""OmniParser 界面检测：懒启动独立 worker，解析可点框。

主进程只发 HTTP，不加载 YOLO。首次 `locate` 再拉 worker；失败由调用方跳过。
"""

from __future__ import annotations

import asyncio
import atexit
import ipaddress
import os
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from max_gui.config import MissingVllmError, Settings
from max_gui.inference.ocr import resolve_vllm_python
from max_gui.lifecycle import resolve_vllm_bin

LOCATE_SKIP_MESSAGE = "界面定位不可用，请仅根据已有截图继续。"
LOCATE_EMPTY_MESSAGE = "界面定位未检出可点控件，请仅根据已有截图继续。"

StartFn = Callable[[], subprocess.Popen[bytes]]
HealthyFn = Callable[[], Awaitable[bool]]
ParseFn = Callable[[Path], Awaitable[list["DetectedBox"]]]

_OWNED: list[Any] = []


class LocateUnavailable(RuntimeError):
    """检测进程不可用或返回无法使用的结果。"""


def omniparser_base_url_is_local(settings: Settings) -> bool:
    """判断路径协议的 OmniParser 地址是否为本机 loopback。

    worker 当前接收主进程文件系统中的绝对图像路径，因此不能连接到远端主机。
    """
    try:
        host = urlparse(settings.omniparser_base_url).hostname
    except ValueError:
        return False
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True, slots=True)
class DetectedBox:
    """检测器给出的一个框，坐标在原图或归一化空间。

    字段：
        x1 / y1 / x2 / y2: 左上与右下。
        label: 给模型看的短文本。
        role: 粗类别，如 `icon` / `button` / `text`。
        score: 越大越优先保留；缺省 0。
        normalized: 为真时坐标是 0–1 相对原图。
    """

    x1: float
    y1: float
    x2: float
    y2: float
    label: str
    role: str = "icon"
    score: float = 0.0
    normalized: bool = False


def omniparser_host_port(settings: Settings) -> tuple[str, int]:
    """从 `omniparser_base_url` 解析监听地址，缺省 `127.0.0.1:8002`。"""
    parsed = urlparse(settings.omniparser_base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8002
    return host, port


def resolve_omniparser_python(*, vllm_bin: Path | None = None) -> Path:
    """定位 worker 解释器：环境变量、vLLM 旁 Python，最后才是当前解释器。"""
    env = os.environ.get("MAX_GUI_OMNIPARSER_PYTHON")
    if env:
        path = Path(env).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path
        raise LocateUnavailable(f"MAX_GUI_OMNIPARSER_PYTHON 不可执行：{env}")
    try:
        return resolve_vllm_python(vllm_bin=vllm_bin or resolve_vllm_bin())
    except MissingVllmError:
        return Path(sys.executable)


def omniparser_serve_command(settings: Settings) -> list[str]:
    """构造 OmniParser worker 启动命令。"""
    host, port = omniparser_host_port(settings)
    return [
        str(resolve_omniparser_python()),
        str(_worker_path()),
        "--host",
        host,
        "--port",
        str(port),
        "--weights",
        str(settings.omniparser_model_path),
    ]


def _worker_path() -> Path:
    """worker 脚本路径。"""
    return Path(__file__).resolve().with_name("omniparser_worker.py")


def omniparser_log_path(settings: Settings) -> Path:
    """worker 标准输出与错误的落盘路径。"""
    return Path(settings.project_root) / "artifacts" / "logs" / "omniparser.log"


def _read_log_tail(path: Path, *, limit: int = 400) -> str:
    """读日志末尾一小段，供跳过文案引用。"""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    text = data[-4000:].decode("utf-8", errors="replace").strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    snippet = "；".join(lines[-6:])
    if len(snippet) > limit:
        return snippet[-limit:]
    return snippet


class LocateRuntime:
    """按进程复用的定位服务：首次调用再启动，退出时只杀自己拉起的进程。"""

    def __init__(
        self,
        settings: Settings,
        *,
        start_fn: StartFn | None = None,
        healthy_fn: HealthyFn | None = None,
        parse_fn: ParseFn | None = None,
    ) -> None:
        """参数：`settings` 提供地址与超时；其余为测试注入。"""
        self.settings = settings
        self._start_fn = start_fn
        self._healthy_fn = healthy_fn
        self._parse_fn = parse_fn
        self._lock = asyncio.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle: Any = None
        self._owned = False
        self.start_count = 0

    async def parse(self, path: Path) -> list[DetectedBox]:
        """确保服务就绪后解析图像上的可点框。

        参数：
            path: 已校验过的本地图像。

        返回：
            检测框列表，可能为空。

        异常：
            LocateUnavailable: 启动或推理失败。
        """
        if not omniparser_base_url_is_local(self.settings):
            raise LocateUnavailable("OmniParser 仅支持本机 loopback 地址，无法传递本地图片路径")
        if self._parse_fn is not None:
            try:
                return await self._parse_fn(path)
            except LocateUnavailable:
                raise
            except Exception as exc:
                raise LocateUnavailable(str(exc) or "定位失败") from exc
        try:
            await self.ensure_server()
            return await self._parse_http(path)
        except LocateUnavailable:
            raise
        except Exception as exc:
            raise LocateUnavailable(str(exc) or "定位失败") from exc

    async def ensure_server(self) -> None:
        """已健康则复用；否则启动 worker 并等到就绪。"""
        async with self._lock:
            if await self._healthy():
                return
            self._start_server()
            deadline = time.monotonic() + self.settings.omniparser_start_timeout
            while time.monotonic() < deadline:
                if await self._healthy():
                    return
                if self._process is not None and self._process.poll() is not None:
                    break
                await asyncio.sleep(0.25)
            raise LocateUnavailable(self._format_startup_failure())

    def shutdown(self) -> None:
        """只终止本运行时拉起的进程；外部已在监听的实例不杀。"""
        if not self._owned or self._process is None:
            return
        process = self._process
        self._process = None
        self._owned = False
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        handle = self._log_handle
        self._log_handle = None
        if handle is not None:
            handle.close()

    def _start_server(self) -> None:
        """拉起 worker 子进程并登记为自有。"""
        if self._process is not None and self._process.poll() is None:
            return
        self.start_count += 1
        if self._start_fn is not None:
            self._process = self._start_fn()
        else:
            command = omniparser_serve_command(self.settings)
            log_path = omniparser_log_path(self.settings)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handle = log_path.open("ab")
            handle.write(f"\n--- start {' '.join(command)} ---\n".encode())
            handle.flush()
            self._log_handle = handle
            self._process = subprocess.Popen(
                command,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
        self._owned = True
        _register(self)

    def _format_startup_failure(self) -> str:
        """拼启动失败原因：退出码、日志尾、日志路径。"""
        log_path = omniparser_log_path(self.settings)
        parts = ["OmniParser 未能就绪"]
        code = self._process.poll() if self._process is not None else None
        if code is not None:
            parts.append(f"退出码 {code}")
        tail = _read_log_tail(log_path)
        if tail:
            parts.append(tail)
        parts.append(f"详见 {log_path}")
        return "；".join(parts)

    async def _healthy(self) -> bool:
        """探测 `/health`。"""
        if self._healthy_fn is not None:
            return await self._healthy_fn()
        url = self.settings.omniparser_base_url.rstrip("/") + "/health"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def _parse_http(self, path: Path) -> list[DetectedBox]:
        """POST `/parse` 并把 JSON 收成 `DetectedBox`。"""
        url = self.settings.omniparser_base_url.rstrip("/") + "/parse"
        async with httpx.AsyncClient(timeout=self.settings.omniparser_timeout) as client:
            response = await client.post(url, json={"path": str(path)})
            response.raise_for_status()
            data = response.json()
        raw_boxes = data.get("boxes") if isinstance(data, dict) else None
        if not isinstance(raw_boxes, list):
            raise LocateUnavailable("定位结果无法解析")
        boxes: list[DetectedBox] = []
        for item in raw_boxes:
            parsed = _box_from_mapping(item) if isinstance(item, dict) else None
            if parsed is not None:
                boxes.append(parsed)
        return boxes


def _box_from_mapping(item: dict[str, Any]) -> DetectedBox | None:
    """从 worker JSON 抽一个框；缺坐标则丢弃。"""
    try:
        x1 = float(item["x1"])
        y1 = float(item["y1"])
        x2 = float(item["x2"])
        y2 = float(item["y2"])
    except (KeyError, TypeError, ValueError):
        return None
    label = str(item.get("label") or item.get("content") or item.get("text") or "").strip()
    role = str(item.get("role") or item.get("type") or "icon").strip() or "icon"
    try:
        score = float(item.get("score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    normalized = bool(item.get("normalized"))
    if not label:
        label = role
    return DetectedBox(
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        label=label,
        role=role,
        score=score,
        normalized=normalized,
    )


def _register(runtime: LocateRuntime) -> None:
    """记下自有运行时，供退出时统一关闭。"""
    if runtime not in _OWNED:
        _OWNED.append(runtime)


def shutdown_owned_locate() -> None:
    """终止本进程拉起的全部 OmniParser 子进程。"""
    while _OWNED:
        _OWNED.pop().shutdown()


atexit.register(shutdown_owned_locate)
