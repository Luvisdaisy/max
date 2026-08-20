"""工具层：工作区读写/搜索、确认门，以及桌面工具行为。"""

from __future__ import annotations

import json

from max_gui.config import Settings
from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.tools.desktop import (
    clear_desktop_context,
    current_locate_hits,
    restore_desktop_context,
    snapshot_desktop_context,
    store_locate_hits,
)
from max_gui.tools.protocol import ToolResult
from max_gui.tools.registry import DenyGate, SessionScopedGate, build_default_registry


def _text(result: str | ToolResult) -> str:
    """工具返回值的文本部分，便于断言。"""
    return result.text if isinstance(result, ToolResult) else str(result)


async def test_read_file_and_reject_escape(settings: Settings) -> None:
    """能读工作区内文件，拒绝逃出工作区的路径。"""
    notes = settings.workspace / "notes.md"
    notes.write_text("hello workspace", encoding="utf-8")
    registry = build_default_registry(settings, desktop=FakeDesktopBackend())
    assert "hello workspace" == await registry.invoke("read_file", {"path": "notes.md"})
    denied = await registry.invoke("read_file", {"path": "../outside.txt"})
    assert "权限" in denied


async def test_search_files(settings: Settings) -> None:
    """按内容搜索返回路径与摘录。"""
    (settings.workspace / "a.txt").write_text("alpha token here", encoding="utf-8")
    registry = build_default_registry(settings, desktop=FakeDesktopBackend())
    result = await registry.invoke("search_files", {"query": "token"})
    assert "a.txt" in result
    assert "token" in result


async def test_unknown_tool_and_confirmation_deny(settings: Settings) -> None:
    """未知工具报错；拒绝确认时不写文件。"""
    registry = build_default_registry(settings, gate=DenyGate(), desktop=FakeDesktopBackend())
    unknown = await registry.invoke("not_a_tool", {})
    assert "未知工具" in unknown
    cancelled = await registry.invoke("write_file", {"path": "x.txt", "content": "nope"})
    assert "已取消" in cancelled
    assert not (settings.workspace / "x.txt").exists()


async def test_run_python_is_unknown(settings: Settings) -> None:
    """默认注册表不再暴露 `run_python`，调用按未知工具处理。"""
    registry = build_default_registry(settings, desktop=FakeDesktopBackend())
    names = [schema["function"]["name"] for schema in registry.schemas()]
    assert "run_python" not in names
    result = await registry.invoke("run_python", {"code": "print(1)"})
    assert "未知工具" in result


def _desktop_registry(settings: Settings, *, gate=None, backend: FakeDesktopBackend | None = None):
    """装配带假桌面后端的默认注册表，返回 `(registry, backend)`。"""
    clear_desktop_context()
    fake = backend or FakeDesktopBackend()
    return build_default_registry(settings, gate=gate, desktop=fake), fake


async def test_workspace_auto_approve_still_confirms_click(settings: Settings) -> None:
    """只开工作区自动批准时，点击仍需确认，写文件可通过。"""
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
    """开桌面自动批准后 `keyboard_press` 直接执行。"""
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve=False, auto_approve_desktop=True),
    )
    result = await registry.invoke("keyboard_press", {"keys": "enter"})
    assert "已按下 enter" in _text(result)
    assert isinstance(result, ToolResult) and result.images
    assert ("press", {"key": "enter"}) in backend.calls


async def test_desktop_deny_does_not_execute(settings: Settings) -> None:
    """拒绝确认时键盘输入不会打到后端。"""
    registry, backend = _desktop_registry(settings, gate=DenyGate())
    result = await registry.invoke("keyboard_type", {"text": "1+1"})
    assert "已取消" in result
    assert backend.calls == []


async def test_screenshot_returns_image_and_info(settings: Settings) -> None:
    """截图返回落盘图像及含 scale 的摘要。"""
    registry, _backend = _desktop_registry(settings)
    result = await registry.invoke("screenshot", {})
    assert isinstance(result, ToolResult)
    assert result.images and result.images[0].is_file()
    assert "scale" in result.text
    assert '"coordinate_space": "view"' in result.text
    assert "view_width" in result.text
    assert "origin" in result.text
    payload = json.loads(result.text)
    assert payload["cursor"]["y"] <= payload["view_height"]
    assert payload["cursor"]["x"] <= payload["view_width"]


async def test_mouse_move_clamps(settings: Settings) -> None:
    """越界坐标被夹到屏幕内。"""
    registry, backend = _desktop_registry(settings)
    result = await registry.invoke("mouse_move", {"x": 99999, "y": -4})
    assert "夹紧" in result
    assert backend.mouse == (1439, 0)


async def test_keyboard_rejects_unknown_and_dangerous(settings: Settings) -> None:
    """未知键名与 Command+Q 被拒绝且不执行。"""
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve_desktop=True),
    )
    unknown = await registry.invoke("keyboard_press", {"keys": "launch_missiles"})
    assert "未知键名" in unknown
    danger = await registry.invoke("keyboard_press", {"keys": ["command", "q"]})
    assert "危险热键" in danger
    assert backend.calls == []


async def test_keyboard_type_ascii_and_paste(settings: Settings) -> None:
    """ASCII 走 write，中文走剪贴板粘贴。"""
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve_desktop=True),
    )
    ascii_out = await registry.invoke("keyboard_type", {"text": "1+1"})
    assert "write" in _text(ascii_out)
    assert any(call[0] == "write" and call[1]["text"] == "1+1" for call in backend.calls)
    zh = await registry.invoke("keyboard_type", {"text": "你好"})
    assert "剪贴板" in _text(zh)
    assert any(call[0] == "paste" and call[1]["text"] == "你好" for call in backend.calls)


async def test_desktop_closed_loop_fake_backend(settings: Settings) -> None:
    """截图、点击、输入、按键再截图的闭环调用顺序正确。"""
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve_desktop=True),
    )
    shot1 = await registry.invoke("screenshot", {})
    assert isinstance(shot1, ToolResult)
    payload = json.loads(shot1.text)
    click = await registry.invoke(
        "mouse_click",
        {"x": payload["view_width"] // 4, "y": payload["view_height"] // 4},
    )
    typed = await registry.invoke("keyboard_type", {"text": "1+1"})
    pressed = await registry.invoke("keyboard_press", {"keys": "enter"})
    shot2 = await registry.invoke("screenshot", {})
    assert isinstance(shot1, ToolResult) and isinstance(shot2, ToolResult)
    assert "单击" in _text(click) and "write" in _text(typed) and "enter" in _text(pressed)
    assert isinstance(click, ToolResult) and click.images
    names = [call[0] for call in backend.calls]
    assert names.count("screenshot") >= 2
    assert "click" in names and "write" in names and "press" in names


async def test_black_screenshot_is_permission_error(settings: Settings) -> None:
    """全黑截图被当成缺少屏幕录制权限。"""
    registry, _backend = _desktop_registry(
        settings, backend=FakeDesktopBackend(fail_screenshot=True)
    )
    result = await registry.invoke("screenshot", {})
    assert "屏幕录制" in result


async def test_view_coords_convert_after_screenshot(settings: Settings) -> None:
    """截图后的鼠标坐标按视图像素换算成逻辑像素。"""
    registry, backend = _desktop_registry(settings)
    shot = await registry.invoke("screenshot", {})
    assert isinstance(shot, ToolResult)
    payload = json.loads(shot.text)
    view_x = payload["view_width"] // 4
    view_y = payload["view_height"] // 4
    expected_x = round(view_x * payload["width"] / payload["view_width"])
    expected_y = round(view_y * payload["height"] / payload["view_height"])
    moved = await registry.invoke("mouse_move", {"x": view_x, "y": view_y})
    assert "视图像素" in moved
    assert f"({view_x}, {view_y})" in moved
    assert f"逻辑坐标 ({expected_x}, {expected_y})" not in moved
    assert backend.mouse == (expected_x, expected_y)


async def test_region_view_coords_include_origin(settings: Settings) -> None:
    """区域截图后的视图像素要加上逻辑原点。"""
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve_desktop=True),
    )
    shot = await registry.invoke(
        "screenshot", {"region": {"x": 200, "y": 100, "width": 400, "height": 200}}
    )
    assert isinstance(shot, ToolResult)
    payload = json.loads(shot.text)
    view_x, view_y = 10, 15
    expected_x = 200 + round(view_x * payload["width"] / payload["view_width"])
    expected_y = 100 + round(view_y * payload["height"] / payload["view_height"])
    clicked = await registry.invoke("mouse_click", {"x": view_x, "y": view_y})
    assert "视图像素" in _text(clicked)
    assert isinstance(clicked, ToolResult) and clicked.images
    click = next(call for call in backend.calls if call[0] == "click")
    assert click[1]["x"] == expected_x
    assert click[1]["y"] == expected_y


async def test_screenshot_cursor_is_view_pixels(settings: Settings) -> None:
    """摘要光标按视图像素换算，不得超出视图高。"""
    registry, backend = _desktop_registry(settings)
    backend.mouse = (1282, 834)
    backend.screen_size = (1920, 1080)
    result = await registry.invoke("screenshot", {})
    assert isinstance(result, ToolResult)
    payload = json.loads(result.text)
    expected_x = round(1282 * payload["view_width"] / payload["width"])
    expected_y = round(834 * payload["view_height"] / payload["height"])
    assert payload["cursor"] == {"x": expected_x, "y": expected_y}
    assert expected_y <= payload["view_height"]


async def test_view_frame_survives_context_reset(settings: Settings) -> None:
    """模拟跨 worker 丢失 ContextVar 后，从快照恢复仍按视图像素换算。"""
    registry, backend = _desktop_registry(settings)
    shot = await registry.invoke("screenshot", {})
    assert isinstance(shot, ToolResult)
    payload = json.loads(shot.text)
    frame, hits = snapshot_desktop_context()
    clear_desktop_context()
    restore_desktop_context(frame, hits)
    view_x = payload["view_width"] // 4
    view_y = payload["view_height"] // 4
    expected_x = round(view_x * payload["width"] / payload["view_width"])
    expected_y = round(view_y * payload["height"] / payload["view_height"])
    moved = await registry.invoke("mouse_move", {"x": view_x, "y": view_y})
    assert "视图像素" in moved
    assert "尚无截图" not in moved
    assert backend.mouse == (expected_x, expected_y)


async def test_mouse_move_without_screenshot_is_logical(settings: Settings) -> None:
    """尚未截图时坐标按逻辑像素并在结果里说明。"""
    registry, backend = _desktop_registry(settings)
    result = await registry.invoke("mouse_move", {"x": 80, "y": 40})
    assert "尚无截图" in result
    assert "逻辑坐标 (80, 40)" in result
    assert backend.mouse == (80, 40)


async def test_view_out_of_bounds_rejected(settings: Settings) -> None:
    """有截图时视图外坐标拒绝执行，不夹到屏幕边。"""
    registry, backend = _desktop_registry(
        settings, gate=SessionScopedGate(auto_approve_desktop=True)
    )
    shot = await registry.invoke("screenshot", {})
    assert isinstance(shot, ToolResult)
    payload = json.loads(shot.text)
    before = list(backend.calls)
    moved = await registry.invoke("mouse_move", {"x": 0, "y": payload["view_height"]})
    assert "超出最近截图视图" in moved
    assert str(payload["view_height"]) in moved
    assert str(payload["view_width"]) in moved
    assert backend.calls == before
    dragged = await registry.invoke(
        "mouse_drag",
        {
            "x1": 1,
            "y1": 1,
            "x2": 2,
            "y2": payload["view_height"] + 8,
        },
    )
    assert "超出最近截图视图" in dragged
    assert all(call[0] != "drag_to" for call in backend.calls)
    clicked = await registry.invoke("mouse_click", {"x": payload["view_width"], "y": 0})
    assert "超出最近截图视图" in clicked
    assert all(call[0] != "click" for call in backend.calls)


async def test_target_id_ignores_view_bounds(settings: Settings) -> None:
    """定位编号不走视图出界拒绝，摘要在有截图时仍报视图像素。"""
    registry, backend = _desktop_registry(
        settings, gate=SessionScopedGate(auto_approve_desktop=True)
    )
    shot = await registry.invoke("screenshot", {})
    assert isinstance(shot, ToolResult)
    store_locate_hits({1: (220, 80)})
    result = await registry.invoke("mouse_click", {"target_id": 1})
    text = _text(result)
    assert "定位编号" in text
    assert "视图像素" in text
    assert "逻辑坐标 (220, 80)" not in text
    click = next(call for call in backend.calls if call[0] == "click")
    assert click[1]["x"] == 220
    assert click[1]["y"] == 80


async def test_mouse_scroll_requires_desktop_confirm(settings: Settings) -> None:
    """滚动走桌面确认门；批准后假后端记录 clicks。"""
    denied, backend = _desktop_registry(
        settings, gate=SessionScopedGate(auto_approve=True, auto_approve_desktop=False)
    )
    cancelled = await denied.invoke("mouse_scroll", {"clicks": 3})
    assert "已取消" in cancelled
    assert backend.calls == []
    registry, backend = _desktop_registry(
        settings, gate=SessionScopedGate(auto_approve_desktop=True)
    )
    await registry.invoke("screenshot", {})
    result = await registry.invoke("mouse_scroll", {"clicks": 3, "x": 10, "y": 10})
    assert "滚动" in _text(result)
    assert isinstance(result, ToolResult) and result.images
    assert any(call[0] == "scroll" and call[1]["clicks"] == 3 for call in backend.calls)


async def test_locate_hits_survive_context_reset(settings: Settings) -> None:
    """定位编号从快照恢复后仍可按 `target_id` 点击。"""
    registry, backend = _desktop_registry(
        settings, gate=SessionScopedGate(auto_approve_desktop=True)
    )
    store_locate_hits({1: (220, 80)})
    frame, hits = snapshot_desktop_context()
    clear_desktop_context()
    restore_desktop_context(frame, hits)
    result = await registry.invoke("mouse_click", {"target_id": 1})
    assert "定位编号" in _text(result)
    click = next(call for call in backend.calls if call[0] == "click")
    assert click[1]["x"] == 220
    assert click[1]["y"] == 80


async def test_target_id_clicks_locate_center(settings: Settings) -> None:
    """`target_id` 使用最近一次定位的逻辑中心，忽略本次 x/y。"""
    registry, backend = _desktop_registry(
        settings, gate=SessionScopedGate(auto_approve_desktop=True)
    )
    current_locate_hits.set({1: (220, 80)})
    result = await registry.invoke("mouse_click", {"target_id": 1, "x": 1, "y": 1})
    assert "定位编号" in _text(result)
    click = next(call for call in backend.calls if call[0] == "click")
    assert click[1]["x"] == 220
    assert click[1]["y"] == 80
    missing = await registry.invoke("mouse_click", {"target_id": 9})
    assert "没有 id=9" in missing


async def test_mouse_move_does_not_attach_screenshot(settings: Settings) -> None:
    """移动指针成功也不附新截图。"""
    registry, backend = _desktop_registry(settings)
    result = await registry.invoke("mouse_move", {"x": 12, "y": 8})
    assert not isinstance(result, ToolResult)
    assert all(call[0] != "screenshot" for call in backend.calls)


async def test_click_followup_black_screenshot_keeps_action(settings: Settings) -> None:
    """后置截图全黑时保留点击摘要，不把空图回注。"""
    backend = FakeDesktopBackend(fail_screenshot=True)
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve_desktop=True),
        backend=backend,
    )
    result = await registry.invoke("mouse_click", {"x": 10, "y": 10})
    text = _text(result)
    assert "单击" in text
    assert "屏幕录制" in text
    assert isinstance(result, ToolResult)
    assert not result.images
    assert any(call[0] == "click" for call in backend.calls)
