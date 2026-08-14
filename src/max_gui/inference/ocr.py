"""独立 OCR 推理：懒启动 vLLM、Chat Completions，以及 transformers 回退。

支持整图 `OCR:` 与文字定位 `Spotting:`，提示词由调用方传入。
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import subprocess
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from max_gui.config import DEFAULT_OCR_MODEL, MissingVllmError, Settings
from max_gui.lifecycle import resolve_vllm_bin

OCR_PROMPT = "OCR:"
SPOTTING_PROMPT = "Spotting:"
OCR_SKIP_MESSAGE = "OCR 不可用，请仅根据已有截图继续。"
OCR_LOCATE_SKIP_MESSAGE = "文字定位不可用，请仅根据已有截图继续。"
OCR_LOCATE_PARSE_MESSAGE = "无法解析文字定位结果，请仅根据已有截图继续。"
OCR_FALLBACK_NOTE = "（已回退 transformers）"
SPOTTING_MAX_NEW_TOKENS = 2048

StartFn = Callable[[], subprocess.Popen[bytes]]
HealthyFn = Callable[[], Awaitable[bool]]
CompleteFn = Callable[[dict[str, Any]], Awaitable[str]]
TransformersFn = Callable[[Path], Awaitable[str]]

_OWNED: list[Any] = []


class OcrUnavailable(RuntimeError):
    """vLLM 或 transformers 均不可用。"""


def ocr_host_port(settings: Settings) -> tuple[str, int]:
    """从 `ocr_base_url` 解析监听地址，缺省 `127.0.0.1:8001`。"""
    parsed = urlparse(settings.ocr_base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8001
    return host, port


def ocr_serve_command(settings: Settings, *, vllm_bin: Path | None = None) -> list[str]:
    """构造 OCR 专用 `vllm serve`，不含 Qwen tool parser。"""
    binary = vllm_bin or resolve_vllm_bin()
    host, port = ocr_host_port(settings)
    return [
        str(binary),
        "serve",
        str(settings.ocr_model_path),
        "--host",
        host,
        "--port",
        str(port),
        "--trust-remote-code",
        "--max-num-batched-tokens",
        "16384",
        "--no-enable-prefix-caching",
        "--mm-processor-cache-gb",
        "0",
        "--gpu-memory-utilization",
        str(settings.ocr_gpu_memory_utilization),
        "--dtype",
        settings.dtype,
        "--served-model-name",
        DEFAULT_OCR_MODEL,
    ]


def resolve_vllm_python(*, vllm_bin: Path | None = None) -> Path:
    """vLLM 二进制同目录下的 Python，供 transformers 子进程使用。"""
    binary = vllm_bin or resolve_vllm_bin()
    for name in ("python", "python3"):
        candidate = binary.parent / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise MissingVllmError()


def _worker_path() -> Path:
    return Path(__file__).resolve().with_name("ocr_transformers_worker.py")


class OcrRuntime:
    """按进程复用的 OCR 服务：首次调用再启动，退出时只杀自己拉起的进程。"""

    def __init__(
        self,
        settings: Settings,
        *,
        start_fn: StartFn | None = None,
        healthy_fn: HealthyFn | None = None,
        complete_fn: CompleteFn | None = None,
        transformers_fn: TransformersFn | None = None,
    ) -> None:
        self.settings = settings
        self._start_fn = start_fn
        self._healthy_fn = healthy_fn
        self._complete_fn = complete_fn
        self._transformers_fn = transformers_fn
        self._lock = asyncio.Lock()
        self._process: subprocess.Popen[bytes] | None = None
        self._owned = False
        self.start_count = 0

    async def recognize(
        self,
        path: Path,
        image_part: dict[str, Any],
        *,
        prompt: str = OCR_PROMPT,
        max_new_tokens: int | None = None,
        skip_message: str = OCR_SKIP_MESSAGE,
    ) -> str:
        """先 vLLM，失败再阻塞走 transformers；仍失败则返回可跳过文案。

        参数：
            path: 原图路径，供 transformers 回退。
            image_part: 已编码的 `image_url` 部件。
            prompt: 任务提示，默认 `OCR:`。
            max_new_tokens: 可选生成上限；`None` 用服务默认。
            skip_message: 两档都失败时的中文说明。
        """
        try:
            await self.ensure_server()
            return await self._complete(image_part, prompt=prompt, max_new_tokens=max_new_tokens)
        except Exception:
            pass
        try:
            text = await self._transformers(path, prompt=prompt, max_new_tokens=max_new_tokens)
            note = "" if OCR_FALLBACK_NOTE in text else f"\n{OCR_FALLBACK_NOTE}"
            return f"{text}{note}"
        except Exception:
            return skip_message

    async def ensure_server(self) -> None:
        """已健康则复用；否则启动一个 OCR vLLM 并等到就绪。"""
        async with self._lock:
            if await self._healthy():
                return
            self._start_server()
            deadline = time.monotonic() + self.settings.ocr_start_timeout
            while time.monotonic() < deadline:
                if await self._healthy():
                    return
                if self._process is not None and self._process.poll() is not None:
                    break
                await asyncio.sleep(0.25)
            raise OcrUnavailable("OCR vLLM 未能就绪")

    def shutdown(self) -> None:
        """只终止本运行时拉起的进程；外部已在监听的实例不杀。"""
        if not self._owned or self._process is None:
            return
        process = self._process
        self._process = None
        self._owned = False
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    def _start_server(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        self.start_count += 1
        if self._start_fn is not None:
            self._process = self._start_fn()
        else:
            command = ocr_serve_command(self.settings)
            env = os.environ.copy()
            env.setdefault("VLLM_HOST_IP", "127.0.0.1")
            env.setdefault("MASTER_ADDR", "127.0.0.1")
            env.setdefault("GLOO_SOCKET_IFNAME", "lo0")
            self._process = subprocess.Popen(
                command,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        self._owned = True
        _register(self)

    async def _healthy(self) -> bool:
        if self._healthy_fn is not None:
            return await self._healthy_fn()
        url = self.settings.ocr_base_url.rstrip("/") + "/models"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def _complete(
        self,
        image_part: dict[str, Any],
        *,
        prompt: str,
        max_new_tokens: int | None,
    ) -> str:
        if self._complete_fn is not None:
            return await self._complete_fn(image_part)
        payload: dict[str, Any] = {
            "model": DEFAULT_OCR_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [image_part, {"type": "text", "text": prompt}],
                }
            ],
            "temperature": 0,
            "stream": False,
        }
        if max_new_tokens is not None:
            payload["max_tokens"] = max_new_tokens
        url = self.settings.ocr_base_url.rstrip("/") + "/chat/completions"
        headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        async with httpx.AsyncClient(timeout=self.settings.ocr_timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        text = str(data["choices"][0]["message"]["content"] or "").strip()
        if not text:
            raise OcrUnavailable("OCR 返回空文本")
        return text

    async def _transformers(
        self,
        path: Path,
        *,
        prompt: str,
        max_new_tokens: int | None,
    ) -> str:
        if self._transformers_fn is not None:
            return await self._transformers_fn(path)
        return await asyncio.to_thread(self._run_transformers_worker, path, prompt, max_new_tokens)

    def _run_transformers_worker(self, path: Path, prompt: str, max_new_tokens: int | None) -> str:
        python = resolve_vllm_python()
        command = [
            str(python),
            str(_worker_path()),
            "--model",
            str(self.settings.ocr_model_path),
            "--image",
            str(path),
            "--prompt",
            prompt,
        ]
        if max_new_tokens is not None:
            command.extend(["--max-new-tokens", str(max_new_tokens)])
        timeout = self.settings.ocr_start_timeout + self.settings.ocr_timeout
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrUnavailable("transformers 回退超时") from exc
        if completed.returncode != 0:
            raise OcrUnavailable(completed.stderr.strip() or completed.stdout.strip() or "回退失败")
        payload = json.loads(completed.stdout)
        if payload.get("error"):
            raise OcrUnavailable(str(payload["error"]))
        text = str(payload.get("text") or "").strip()
        if not text:
            raise OcrUnavailable("transformers 返回空文本")
        return text


def _register(runtime: OcrRuntime) -> None:
    if runtime not in _OWNED:
        _OWNED.append(runtime)


def shutdown_owned_ocr() -> None:
    """终止本进程拉起的全部 OCR 子进程。"""
    while _OWNED:
        _OWNED.pop().shutdown()


atexit.register(shutdown_owned_ocr)
