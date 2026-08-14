from __future__ import annotations

from max_gui.config import Settings
from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.tools.protocol import ToolResult
from max_gui.tools.registry import DenyGate, SessionScopedGate, build_default_registry


async def test_read_file_and_reject_escape(settings: Settings) -> None:
    notes = settings.workspace / "notes.md"
    notes.write_text("hello workspace", encoding="utf-8")
    registry = build_default_registry(settings, desktop=FakeDesktopBackend())
    assert "hello workspace" == await registry.invoke("read_file", {"path": "notes.md"})
    denied = await registry.invoke("read_file", {"path": "../outside.txt"})
    assert "权限" in denied


async def test_search_files(settings: Settings) -> None:
    (settings.workspace / "a.txt").write_text("alpha token here", encoding="utf-8")
    registry = build_default_registry(settings, desktop=FakeDesktopBackend())
    result = await registry.invoke("search_files", {"query": "token"})
    assert "a.txt" in result
    assert "token" in result


async def test_run_python_success_and_timeout(settings: Settings) -> None:
    registry = build_default_registry(settings, desktop=FakeDesktopBackend())
    ok = await registry.invoke("run_python", {"code": "print(1+1)"})
    assert "2" in ok
    assert "exit: 0" in ok
    timed = await registry.invoke("run_python", {"code": "import time; time.sleep(5)"})
    assert "超时" in timed


async def test_unknown_tool_and_confirmation_deny(settings: Settings) -> None:
    registry = build_default_registry(settings, gate=DenyGate(), desktop=FakeDesktopBackend())
    unknown = await registry.invoke("not_a_tool", {})
    assert "未知工具" in unknown
    cancelled = await registry.invoke("write_file", {"path": "x.txt", "content": "nope"})
    assert "已取消" in cancelled
    assert not (settings.workspace / "x.txt").exists()
    cancelled_py = await registry.invoke("run_python", {"code": "print(1)"})
    assert "已取消" in cancelled_py


def _desktop_registry(settings: Settings, *, gate=None, backend: FakeDesktopBackend | None = None):
    fake = backend or FakeDesktopBackend()
    return build_default_registry(settings, gate=gate, desktop=fake), fake


async def test_workspace_auto_approve_still_confirms_click(settings: Settings) -> None:
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve=True, auto_approve_desktop=False),
    )
    result = await registry.invoke("mouse_click", {"x": 10, "y": 10})
    assert "已取消" in result
    assert backend.calls == []
    written = await registry.invoke("write_file", {"path": "ok.txt", "content": "yes"})
    assert "已写入" in written


async def test_desktop_auto_approve_skips_press(settings: Settings) -> None:
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve=False, auto_approve_desktop=True),
    )
    result = await registry.invoke("keyboard_press", {"keys": "enter"})
    assert "已按下 enter" in result
    assert ("press", {"key": "enter"}) in backend.calls


async def test_desktop_deny_does_not_execute(settings: Settings) -> None:
    registry, backend = _desktop_registry(settings, gate=DenyGate())
    result = await registry.invoke("keyboard_type", {"text": "1+1"})
    assert "已取消" in result
    assert backend.calls == []


async def test_screenshot_returns_image_and_info(settings: Settings) -> None:
    registry, _backend = _desktop_registry(settings)
    result = await registry.invoke("screenshot", {})
    assert isinstance(result, ToolResult)
    assert result.images and result.images[0].is_file()
    assert "scale" in result.text
    assert "coordinate_space" in result.text


async def test_mouse_move_clamps(settings: Settings) -> None:
    registry, backend = _desktop_registry(settings)
    result = await registry.invoke("mouse_move", {"x": 99999, "y": -4})
    assert "夹紧" in result
    assert backend.mouse == (1439, 0)


async def test_keyboard_rejects_unknown_and_dangerous(settings: Settings) -> None:
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve_desktop=True),
    )
    unknown = await registry.invoke("keyboard_press", {"keys": "launch_missiles"})
    assert "未知键名" in unknown
    danger = await registry.invoke("keyboard_press", {"keys": ["command", "q"]})
    assert "危险热键" in danger
    assert backend.calls == []


async def test_run_python_blocks_pyautogui(settings: Settings) -> None:
    registry, _backend = _desktop_registry(settings)
    blocked = await registry.invoke("run_python", {"code": "import pyautogui"})
    assert "禁止" in blocked
    from_import = await registry.invoke("run_python", {"code": "from pynput import mouse"})
    assert "禁止" in from_import


async def test_keyboard_type_ascii_and_paste(settings: Settings) -> None:
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve_desktop=True),
    )
    ascii_out = await registry.invoke("keyboard_type", {"text": "1+1"})
    assert "write" in ascii_out
    assert any(call[0] == "write" and call[1]["text"] == "1+1" for call in backend.calls)
    zh = await registry.invoke("keyboard_type", {"text": "你好"})
    assert "剪贴板" in zh
    assert any(call[0] == "paste" and call[1]["text"] == "你好" for call in backend.calls)


async def test_desktop_closed_loop_fake_backend(settings: Settings) -> None:
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve_desktop=True),
    )
    shot1 = await registry.invoke("screenshot", {})
    click = await registry.invoke("mouse_click", {"x": 100, "y": 80})
    typed = await registry.invoke("keyboard_type", {"text": "1+1"})
    pressed = await registry.invoke("keyboard_press", {"keys": "enter"})
    shot2 = await registry.invoke("screenshot", {})
    assert isinstance(shot1, ToolResult) and isinstance(shot2, ToolResult)
    assert "单击" in click and "write" in typed and "enter" in pressed
    names = [call[0] for call in backend.calls]
    assert names.count("screenshot") >= 2
    assert "click" in names and "write" in names and "press" in names


async def test_black_screenshot_is_permission_error(settings: Settings) -> None:
    registry, _backend = _desktop_registry(
        settings, backend=FakeDesktopBackend(fail_screenshot=True)
    )
    result = await registry.invoke("screenshot", {})
    assert "屏幕录制" in result
