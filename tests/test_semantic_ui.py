"""双通道 UI 快照和语义工具的组件测试。

这些用例通过可记录 fake 后端验证版本失效、后端分派与文件路径边界，不依赖真实
Chrome、辅助功能权限或屏幕坐标。
"""

from __future__ import annotations

import pytest

from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.desktop.macos_ax import MacOSAXUIBackend
from max_gui.desktop.ui_backends import FakeBrowserBackend, FakeMacOSAXBackend
from max_gui.tools.registry import AutoApproveGate, build_default_registry
from max_gui.ui import StaleUIError, UIElement, UIRegistry


def _element(*, backend: str = "browser", editable: bool = False) -> UIElement:
    """构造仅供测试的未编号结构化元素，真实编号由 `UIRegistry` 重建。"""
    return UIElement(
        id="",
        role="textbox" if editable else "button",
        name="测试控件",
        text=None,
        visible=True,
        enabled=True,
        editable=editable,
        focused=False,
        app_id="chrome" if backend == "browser" else "com.example.app",
        window_id="window-1",
        backend=backend,  # type: ignore[arg-type]
        locator={"fake": True},
    )


def test_ui_registry_replaces_versions_and_hides_locator() -> None:
    """新快照作废旧版本，模型摘要不含 locator 或边界坐标。"""
    registry = UIRegistry()
    first = registry.replace(frame_path="first.png", context="browser", elements=[_element()])
    summary = first.summary()
    assert summary["elements"][0]["id"] == "e_1"
    assert "locator" not in summary["elements"][0]
    second = registry.replace(frame_path="second.png", context="browser", elements=[_element()])
    assert second.version == first.version + 1
    with pytest.raises(StaleUIError):
        registry.resolve(element_id="e_1", version=first.version)


async def test_browser_click_uses_fake_backend_without_desktop_path(settings) -> None:
    """browser 元素点击只调用 locator 后端，不触发任何桌面坐标工具。"""
    browser = FakeBrowserBackend()
    registry = build_default_registry(settings, gate=AutoApproveGate(), browser=browser)
    snapshot = registry.ui_registry.replace(
        frame_path="current.png", context="browser", elements=[_element()]
    )
    result = await registry.invoke("click", {"element_id": "e_1", "ui_version": snapshot.version})
    assert result.ok
    assert browser.calls == [("click", "e_1")]


async def test_ax_input_uses_fake_backend(settings) -> None:
    """native 可编辑元素写入时只调用 AXValue 后端。"""
    ax = FakeMacOSAXBackend()
    registry = build_default_registry(settings, gate=AutoApproveGate(), macos_ax=ax)
    snapshot = registry.ui_registry.replace(
        frame_path="current.png",
        context="native",
        elements=[_element(backend="macos_ax", editable=True)],
    )
    result = await registry.invoke(
        "type_text", {"element_id": "e_1", "ui_version": snapshot.version, "text": "secret"}
    )
    assert result.ok
    assert ax.calls == [("set_value", "e_1")]


async def test_file_input_rejects_outside_workspace(settings, tmp_path) -> None:
    """上传快路径拒绝工作区外文件，且不会分派浏览器调用。"""
    browser = FakeBrowserBackend()
    registry = build_default_registry(settings, gate=AutoApproveGate(), browser=browser)
    snapshot = registry.ui_registry.replace(
        frame_path="current.png", context="browser", elements=[_element()]
    )
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")
    result = await registry.invoke(
        "set_file_input",
        {"element_id": "e_1", "ui_version": snapshot.version, "file_path": str(outside)},
    )
    assert not result.ok
    assert result.code == "tool_error"
    assert browser.calls == []


async def test_browser_drag_and_native_activation_use_matching_backends(settings) -> None:
    """拖放与应用激活都只交给元素所属的结构化后端。"""
    browser = FakeBrowserBackend()
    ax = FakeMacOSAXBackend()
    registry = build_default_registry(
        settings, gate=AutoApproveGate(), browser=browser, macos_ax=ax
    )
    browser_snapshot = registry.ui_registry.replace(
        frame_path="browser.png", context="browser", elements=[_element(), _element()]
    )
    drag_result = await registry.invoke(
        "drag",
        {
            "element_id": "e_1",
            "target_element_id": "e_2",
            "ui_version": browser_snapshot.version,
        },
    )
    assert drag_result.ok and browser.calls == [("drag", "e_1")]
    native_snapshot = registry.ui_registry.replace(
        frame_path="native.png", context="native", elements=[_element(backend="macos_ax")]
    )
    activation = await registry.invoke("activate_app", {"app_id": "com.example.app"})
    assert activation.ok and native_snapshot.context == "native"
    assert ax.calls == [("activate", "com.example.app")]


async def test_semantic_key_tools_use_desktop_backend(settings) -> None:
    """按键与快捷键保留桌面确认边界，真实执行委托既有桌面后端。"""
    desktop = FakeDesktopBackend()
    registry = build_default_registry(settings, gate=AutoApproveGate(), desktop=desktop)
    key_result = await registry.invoke("press_key", {"key": "enter"})
    shortcut_result = await registry.invoke("press_shortcut", {"keys": ["command", "l"]})
    assert key_result.ok and shortcut_result.ok
    assert [name for name, _ in desktop.calls] == ["press", "hotkey"]


def test_macos_ax_readonly_observation_degrades_without_permission() -> None:
    """真实 AX 后端在未授权或无可访问前台元素时安全返回空列表。"""
    assert isinstance(MacOSAXUIBackend().observe(), list)
