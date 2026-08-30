"""受控 Chrome 与 Playwright 浏览器后端的集成测试。

用例只启动 `max-gui` 自己的临时 profile 和回环调试端口，不读取用户现有 Chrome
资料；若本机没有 Chrome 则跳过，而非伪造浏览器端到端证据。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import max_gui.desktop.chrome_session as chrome_session_module
from max_gui.browser import PlaywrightBrowserBackend
from max_gui.desktop.chrome_session import ControlledChromeSession
from max_gui.ui import UIRegistry


def test_browser_backend_rejects_non_loopback_endpoint() -> None:
    """非回环 CDP 地址在连接前被拒绝，避免接管用户或远程浏览器。"""
    with pytest.raises(ValueError, match=r"127\.0\.0\.1"):
        PlaywrightBrowserBackend("http://localhost:9222")


def test_controlled_chrome_start_failure_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    """回环端口或 Chrome 启动失败时转成可降级错误并清理临时资源。"""

    def fail_port() -> int:
        """模拟受限环境无法绑定回环端口。"""
        raise PermissionError("socket denied")

    monkeypatch.setattr(chrome_session_module, "_free_loopback_port", fail_port)
    session = ControlledChromeSession()
    with pytest.raises(RuntimeError, match="无法启动受控 Chrome"):
        session.start()
    assert session.process is None
    assert session.port is None


async def test_controlled_chrome_form_actions(settings) -> None:
    """临时受控 Chrome 可观察 DOM，并执行填充、选择和文件上传快路径。"""
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not chrome.is_file():
        pytest.skip("本机未安装 Google Chrome，无法执行受控浏览器集成测试")
    session = ControlledChromeSession(chrome_path=str(chrome))
    endpoint = session.start()
    backend = PlaywrightBrowserBackend(endpoint)
    try:
        for _ in range(30):
            if await backend.observe() is not None:
                break
            await asyncio.sleep(0.1)
        await backend.navigate(
            "data:text/html,<button>Continue</button><input aria-label=Name><select "
            "aria-label=Kind><option value=one>One</option><option value=two>Two</option>"
            "</select><input type=file aria-label=Upload>"
        )
        observed = await backend.observe()
        assert observed is not None
        _, elements = observed
        registry = UIRegistry()
        snapshot = registry.replace(frame_path="browser.png", context="browser", elements=elements)
        by_label = {item.name: item for item in snapshot.elements}
        await backend.fill(by_label["Name"], "Ada")
        await backend.select_option(by_label["Kind"], "two")
        upload = settings.workspace / "upload.txt"
        upload.write_text("fixture", encoding="utf-8")
        await backend.set_file_input(by_label["Upload"], str(upload))
        await backend.click(by_label["Continue"])
    finally:
        await backend.close()
        session.close()
