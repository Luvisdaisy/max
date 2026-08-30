"""受控 Chrome 的 Playwright UI 后端。

本模块只接受本机回环 CDP 端点，页面 locator 和 DOM 仅保留在进程内；对模型与
会话只输出有限可交互元素摘要。Playwright 未安装或连接失败时安全返回不可用。
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from max_gui.ui import UIElement


class PlaywrightBrowserBackend:
    """通过异步 Playwright 连接受控 Chrome，并按 locator 执行网页动作。"""

    def __init__(self, endpoint: str) -> None:
        """参数：`endpoint` 必须是 `http://127.0.0.1:<port>` 的 CDP 地址。"""
        parsed = urlparse(endpoint)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
            raise ValueError("浏览器调试端点必须是带端口的 http://127.0.0.1 地址")
        self.endpoint = endpoint.rstrip("/")
        self._playwright: Any = None
        self._browser: Any = None

    async def observe(self) -> tuple[str, list[UIElement]] | None:
        """提取当前页面有限交互元素；浏览器不可用时返回空。"""
        page = await self._page()
        if page is None:
            return None
        try:
            await page.bring_to_front()
            raw = await page.locator(
                "button,input,textarea,select,a[href],[role=button],[role=link],"
                "[role=checkbox],[role=radio],[role=tab],[role=menuitem]"
            ).evaluate_all(
                """nodes => nodes.slice(0, 80).map((node, index) => ({
                    index,
                    tag: node.tagName.toLowerCase(),
                    role: node.getAttribute('role') || node.tagName.toLowerCase(),
                    name: node.getAttribute('aria-label') || node.innerText || node.value ||
                        node.getAttribute('title') || node.getAttribute('name') || '',
                    visible: !!(node.offsetWidth || node.offsetHeight || node.getClientRects().length),
                    enabled: !node.disabled && node.getAttribute('aria-disabled') !== 'true',
                    editable: ['input', 'textarea'].includes(node.tagName.toLowerCase()) ||
                        node.getAttribute('contenteditable') === 'true',
                    file: node.tagName.toLowerCase() === 'input' && node.type === 'file',
                    select: node.tagName.toLowerCase() === 'select'
                }))"""
            )
        except Exception:
            return None
        elements: list[UIElement] = []
        for item in raw:
            if not isinstance(item, dict) or not item.get("visible"):
                continue
            index = int(item.get("index") or 0)
            locator = page.locator(
                "button,input,textarea,select,a[href],[role=button],[role=link],"
                "[role=checkbox],[role=radio],[role=tab],[role=menuitem]"
            ).nth(index)
            elements.append(
                UIElement(
                    id="",
                    role=str(item.get("role") or "unknown"),
                    name=str(item.get("name") or "").strip()[:120] or None,
                    text=None,
                    visible=True,
                    enabled=bool(item.get("enabled")),
                    editable=bool(item.get("editable")),
                    focused=False,
                    app_id="chrome",
                    window_id=None,
                    backend="browser",
                    locator={
                        "locator": locator,
                        "file": bool(item.get("file")),
                        "select": bool(item.get("select")),
                    },
                )
            )
        return str(page.url), elements

    async def click(self, element: UIElement, *, double: bool = False) -> None:
        """以当前元素 locator 点击或双击；无 locator 时抛出稳定异常。"""
        locator = self._locator(element)
        if double:
            await locator.dblclick()
        else:
            await locator.click()

    async def fill(self, element: UIElement, text: str, *, clear_first: bool = False) -> None:
        """填充可编辑 locator；Playwright fill 本身会清空旧值。"""
        if not element.editable:
            raise RuntimeError("目标不是可编辑浏览器元素")
        await self._locator(element).fill(text)

    async def select_option(self, element: UIElement, value: str) -> None:
        """只允许原生 select 的 locator 选择指定值。"""
        if not isinstance(element.locator, dict) or not element.locator.get("select"):
            raise RuntimeError("目标不是浏览器下拉选择元素")
        await self._locator(element).select_option(value)

    async def set_file_input(self, element: UIElement, file_path: str) -> None:
        """只允许当前文件 input 直接设置文件，不打开系统文件选择器。"""
        if not isinstance(element.locator, dict) or not element.locator.get("file"):
            raise RuntimeError("目标不是浏览器文件输入元素")
        await self._locator(element).set_input_files(file_path)

    async def scroll(self, element: UIElement, *, delta_y: int) -> None:
        """在元素视区附近滚动指定距离，不把坐标交给模型。"""
        locator = self._locator(element)
        await locator.evaluate("(node, delta) => node.scrollBy(0, delta)", delta_y)

    async def navigate(self, url: str) -> None:
        """导航受控 Chrome 的当前页面，连接不可用时给出稳定诊断。"""
        page = await self._page()
        if page is None:
            raise RuntimeError("受控浏览器当前不可用，请重新观察")
        await page.goto(url)

    async def drag_to(self, source: UIElement, target: UIElement) -> None:
        """使用两个内存 locator 完成网页拖放，绝不传入桌面坐标。"""
        await self._locator(source).drag_to(self._locator(target))

    async def close(self) -> None:
        """释放 Playwright 客户端；不关闭由外部会话管理的 Chrome 进程。"""
        if self._playwright is not None:
            await self._playwright.stop()
        self._playwright = None
        self._browser = None

    async def _page(self) -> Any | None:
        """惰性连接 CDP 并返回第一个可用页面，失败时不向外泄露连接细节。"""
        try:
            if self._browser is None:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.connect_over_cdp(self.endpoint)
            for context in self._browser.contexts:
                if context.pages:
                    return context.pages[-1]
        except Exception:
            await self.close()
        return None

    @staticmethod
    def _locator(element: UIElement) -> Any:
        """取出进程内 locator；元素不属于本后端时拒绝执行。"""
        if element.backend != "browser" or not isinstance(element.locator, dict):
            raise RuntimeError("浏览器元素 locator 已失效")
        locator = element.locator.get("locator")
        if locator is None:
            raise RuntimeError("浏览器元素 locator 已失效")
        return locator
