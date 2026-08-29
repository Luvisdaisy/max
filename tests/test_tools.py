"""工具层：确认门、未知工具，以及桌面工具行为。"""

from __future__ import annotations

import asyncio
import json

import pytest

from max_gui.config import Settings
from max_gui.desktop.fake import FakeDesktopBackend
from max_gui.tools.desktop import (
    ViewFrame,
    active_view_frame,
    clear_desktop_context,
    current_locate_hits,
    current_view_frame,
    restore_desktop_context,
    snapshot_desktop_context,
    store_locate_hits,
    store_view_frame,
)
from max_gui.tools.protocol import Tool, ToolResult
from max_gui.tools.registry import DenyGate, SessionScopedGate, ToolRegistry, build_default_registry


def _text(result: str | ToolResult) -> str:
    """工具返回值的文本部分，便于断言。"""
    return result.text if isinstance(result, ToolResult) else str(result)


async def test_unknown_tool_and_screenshot_skips_gate(settings: Settings) -> None:
    """未知工具报错；截图不再走确认门，DenyGate 也挡不住。"""
    registry = build_default_registry(settings, gate=DenyGate(), desktop=FakeDesktopBackend())
    unknown = await registry.invoke("not_a_tool", {})
    assert "未知工具" in unknown
    shot = await registry.invoke("screenshot", {})
    assert isinstance(shot, ToolResult)
    assert shot.images


def test_registry_filters_strict_schemas_and_marks_side_effects(settings: Settings) -> None:
    """动态 schema 只导出指定工具，且对象层递归拒绝未知字段。"""
    registry = build_default_registry(settings, desktop=FakeDesktopBackend())
    schemas = registry.schemas({"screenshot"})
    assert [item["function"]["name"] for item in schemas] == ["screenshot"]
    parameters = schemas[0]["function"]["parameters"]
    assert parameters["additionalProperties"] is False
    assert parameters["properties"]["region"]["additionalProperties"] is False
    assert registry.is_side_effect("mouse_click")
    assert not registry.is_side_effect("screenshot")


async def test_registry_enforces_real_timeout() -> None:
    """工具实现超过注册表时限时返回稳定 timeout 错误码。"""

    async def slow(_args: dict) -> str:
        """等待到注册表取消，用于验证真实超时。"""
        await asyncio.sleep(0.05)
        return "不应返回"

    registry = ToolRegistry(
        [Tool(name="slow", description="慢工具", parameters={"type": "object"}, invoke=slow)],
        timeout=0.001,
    )
    result = await registry.invoke("slow", {})
    assert isinstance(result, ToolResult)
    assert not result.ok
    assert result.code == "timeout"


async def test_removed_workspace_file_tools_are_unknown(settings: Settings) -> None:
    """默认注册表不再暴露文件读写与搜索，调用按未知工具处理。"""
    registry = build_default_registry(settings, desktop=FakeDesktopBackend())
    names = [schema["function"]["name"] for schema in registry.schemas()]
    removed = (
        "read_file",
        "write_file",
        "list_dir",
        "search_files",
        "run_python",
        "ocr_locate",
    )
    for name in removed:
        assert name not in names
        result = await registry.invoke(name, {})
        assert "未知工具" in result


def _desktop_registry(settings: Settings, *, gate=None, backend: FakeDesktopBackend | None = None):
    """装配带假桌面后端的默认注册表，返回 `(registry, backend)`。"""
    clear_desktop_context()
    fake = backend or FakeDesktopBackend()
    return build_default_registry(settings, gate=gate, desktop=fake), fake


async def test_tools_run_without_auto_approve(settings: Settings) -> None:
    """未开自动批准时截图、按键、点击都立即执行。"""
    registry, backend = _desktop_registry(
        settings,
        gate=SessionScopedGate(auto_approve=False, auto_approve_desktop=False),
    )
    await registry.invoke("screenshot", {})
    pressed = await registry.invoke("keyboard_press", {"keys": ["enter"]})
    assert "已按下 enter" in _text(pressed)
    assert isinstance(pressed, ToolResult) and pressed.images
    await registry.invoke("mouse_move", {"x": 10, "y": 10})
    clicked = await registry.invoke("mouse_click", {})
    assert "单击" in _text(clicked)
    assert any(call[0] == "click" for call in backend.calls)


async def test_keyboard_press_after_screenshot(settings: Settings) -> None:
    """有截图后 `keyboard_press` 直接执行。"""
    registry, backend = _desktop_registry(settings, gate=DenyGate())
    await registry.invoke("screenshot", {})
    result = await registry.invoke("keyboard_press", {"keys": ["enter"]})
    assert "已按下 enter" in _text(result)
    assert ("press", {"key": "enter"}) in backend.calls


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
    """越界坐标被夹到屏幕内，并回注光标截图。"""
    registry, backend = _desktop_registry(settings)
    result = await registry.invoke("mouse_move", {"x": 99999, "y": -4})
    assert "夹紧" in _text(result)
    assert isinstance(result, ToolResult) and result.images
    assert backend.mouse == (1439, 0)


async def test_keyboard_rejects_unknown_and_dangerous(settings: Settings) -> None:
    """未知键名与 Command+Q 被拒绝且不执行。"""
    registry, backend = _desktop_registry(settings)
    await registry.invoke("screenshot", {})
    before = list(backend.calls)
    unknown = await registry.invoke("keyboard_press", {"keys": ["launch_missiles"]})
    assert "未知键名" in unknown
    danger = await registry.invoke("keyboard_press", {"keys": ["command", "q"]})
    assert "危险热键" in danger
    assert backend.calls == before


async def test_keyboard_requires_key_array_and_sends_command_tab(settings: Settings) -> None:
    """仅接受非空字符串数组；Command+Tab 作为一个热键发送。"""
    registry, backend = _desktop_registry(settings)
    await registry.invoke("screenshot", {})
    before = list(backend.calls)
    invalid_values = (
        "command+tab",
        '["command", "tab"]',
        [],
        ["command", 1],
    )
    for keys in invalid_values:
        result = await registry.invoke("keyboard_press", {"keys": keys})
        assert isinstance(result, ToolResult)
        assert not result.ok
        assert result.code == "invalid_arguments"
    assert backend.calls == before

    result = await registry.invoke("keyboard_press", {"keys": ["command", "tab"]})
    assert "已按下 command+tab" in _text(result)
    assert ("hotkey", {"keys": ["command", "tab"]}) in backend.calls


async def test_keyboard_type_ascii_and_paste(settings: Settings) -> None:
    """ASCII 走 write，中文走剪贴板粘贴。"""
    registry, backend = _desktop_registry(settings)
    await registry.invoke("screenshot", {})
    ascii_out = await registry.invoke("keyboard_type", {"text": "1+1"})
    assert "write" in _text(ascii_out)
    assert any(call[0] == "write" and call[1]["text"] == "1+1" for call in backend.calls)
    zh = await registry.invoke("keyboard_type", {"text": "你好"})
    assert "剪贴板" in _text(zh)
    assert any(call[0] == "paste" and call[1]["text"] == "你好" for call in backend.calls)


async def test_desktop_closed_loop_fake_backend(settings: Settings) -> None:
    """截图、移鼠、点击、输入、按键再截图的闭环调用顺序正确。"""
    registry, backend = _desktop_registry(settings)
    shot1 = await registry.invoke("screenshot", {})
    assert isinstance(shot1, ToolResult)
    payload = json.loads(shot1.text)
    await registry.invoke(
        "mouse_move",
        {"x": payload["view_width"] // 4, "y": payload["view_height"] // 4},
    )
    click = await registry.invoke("mouse_click", {})
    typed = await registry.invoke("keyboard_type", {"text": "1+1"})
    pressed = await registry.invoke("keyboard_press", {"keys": ["enter"]})
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
    text = _text(moved)
    assert "视图像素" in text
    assert f"({view_x}, {view_y})" in text
    assert f"逻辑坐标 ({expected_x}, {expected_y})" not in text
    assert backend.mouse == (expected_x, expected_y)
    assert isinstance(moved, ToolResult) and moved.images


async def test_region_view_coords_include_origin(settings: Settings) -> None:
    """区域截图后的视图像素要加上逻辑原点。"""
    registry, backend = _desktop_registry(settings)
    shot = await registry.invoke(
        "screenshot", {"region": {"x": 200, "y": 100, "width": 400, "height": 200}}
    )
    assert isinstance(shot, ToolResult)
    payload = json.loads(shot.text)
    view_x, view_y = 10, 15
    expected_x = 200 + round(view_x * payload["width"] / payload["view_width"])
    expected_y = 100 + round(view_y * payload["height"] / payload["view_height"])
    moved = await registry.invoke("mouse_move", {"x": view_x, "y": view_y})
    assert "视图像素" in _text(moved)
    assert backend.mouse == (expected_x, expected_y)
    clicked = await registry.invoke("mouse_click", {})
    assert "单击" in _text(clicked)
    assert isinstance(clicked, ToolResult) and clicked.images
    click = next(call for call in backend.calls if call[0] == "click")
    assert click[1]["x"] is None
    assert click[1]["y"] is None


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
    assert "视图像素" in _text(moved)
    assert "尚无截图" not in _text(moved)
    assert backend.mouse == (expected_x, expected_y)


async def test_mouse_move_without_screenshot_is_logical(settings: Settings) -> None:
    """尚未截图时坐标按逻辑像素并在结果里说明。"""
    registry, backend = _desktop_registry(settings)
    result = await registry.invoke("mouse_move", {"x": 80, "y": 40})
    text = _text(result)
    assert "尚无截图" in text
    assert "逻辑坐标 (80, 40)" in text
    assert backend.mouse == (80, 40)
    assert isinstance(result, ToolResult) and result.images


async def test_view_out_of_bounds_rejected(settings: Settings) -> None:
    """有截图时视图外坐标拒绝执行，不夹到屏幕边。"""
    registry, backend = _desktop_registry(settings)
    shot = await registry.invoke("screenshot", {})
    assert isinstance(shot, ToolResult)
    payload = json.loads(shot.text)
    before = list(backend.calls)
    moved = await registry.invoke("mouse_move", {"x": 0, "y": payload["view_height"]})
    assert "超出最近截图视图" in moved
    assert str(payload["view_height"]) in moved
    assert str(payload["view_width"]) in moved
    assert backend.calls == before
    await registry.invoke("mouse_move", {"x": 1, "y": 1})
    dragged = await registry.invoke(
        "mouse_drag",
        {
            "x2": 2,
            "y2": payload["view_height"] + 8,
        },
    )
    assert "超出最近截图视图" in dragged
    assert all(call[0] != "drag_to" for call in backend.calls)
    clicked = await registry.invoke("mouse_click", {"x": payload["view_width"], "y": 0})
    assert isinstance(clicked, ToolResult)
    assert clicked.code == "invalid_arguments"
    assert "未知字段" in clicked
    assert all(call[0] != "click" for call in backend.calls)


async def test_target_id_ignores_view_bounds(settings: Settings) -> None:
    """定位编号不走视图出界拒绝，摘要在有截图时仍报视图像素。"""
    registry, backend = _desktop_registry(settings)
    shot = await registry.invoke("screenshot", {})
    assert isinstance(shot, ToolResult)
    store_locate_hits({1: (220, 80)})
    result = await registry.invoke("mouse_move", {"target_id": 1})
    text = _text(result)
    assert "定位编号" in text
    assert "视图像素" in text
    assert "逻辑坐标 (220, 80)" not in text
    assert backend.mouse == (220, 80)


async def test_mouse_scroll_without_confirm(settings: Settings) -> None:
    """滚动不再确认；假后端记录 clicks。"""
    registry, backend = _desktop_registry(
        settings, gate=SessionScopedGate(auto_approve=False, auto_approve_desktop=False)
    )
    await registry.invoke("screenshot", {})
    result = await registry.invoke("mouse_scroll", {"clicks": 3, "x": 10, "y": 10})
    assert "滚动" in _text(result)
    assert isinstance(result, ToolResult) and result.images
    assert any(call[0] == "scroll" and call[1]["clicks"] == 3 for call in backend.calls)


async def test_locate_hits_survive_context_reset(settings: Settings) -> None:
    """定位编号从快照恢复后仍可按 `target_id` 移动。"""
    registry, backend = _desktop_registry(settings)
    store_locate_hits({1: (220, 80)})
    frame, hits = snapshot_desktop_context()
    clear_desktop_context()
    restore_desktop_context(frame, hits)
    result = await registry.invoke("mouse_move", {"target_id": 1})
    assert "定位编号" in _text(result)
    assert backend.mouse == (220, 80)


async def test_target_id_clicks_locate_center(settings: Settings) -> None:
    """`target_id` 使用最近一次定位的逻辑中心，忽略本次 x/y。"""
    registry, backend = _desktop_registry(settings)
    current_locate_hits.set({1: (220, 80)})
    result = await registry.invoke("mouse_move", {"target_id": 1, "x": 1, "y": 1})
    assert "定位编号" in _text(result)
    assert backend.mouse == (220, 80)
    missing = await registry.invoke("mouse_move", {"target_id": 9})
    assert "没有 id=9" in missing
    rejected = await registry.invoke("mouse_click", {"target_id": 1})
    assert isinstance(rejected, ToolResult)
    assert rejected.code == "invalid_arguments"
    assert "未知字段" in rejected


async def test_mouse_move_attaches_screenshot(settings: Settings) -> None:
    """移动指针成功后附带光标截图。"""
    registry, backend = _desktop_registry(settings)
    result = await registry.invoke("mouse_move", {"x": 12, "y": 8})
    assert isinstance(result, ToolResult) and result.images
    assert any(call[0] == "screenshot" for call in backend.calls)


async def test_click_followup_black_screenshot_keeps_action(settings: Settings) -> None:
    """后置截图全黑时保留点击摘要，不把空图回注。"""
    registry, backend = _desktop_registry(settings)
    await registry.invoke("mouse_move", {"x": 10, "y": 10})
    backend.fail_screenshot = True
    result = await registry.invoke("mouse_click", {})
    text = _text(result)
    assert "单击" in text
    assert "屏幕录制" in text
    assert isinstance(result, ToolResult)
    assert not result.images
    assert any(call[0] == "click" for call in backend.calls)


async def test_click_requires_mouse_move_verify(settings: Settings) -> None:
    """只有 screenshot、没有 mouse_move 时拒绝点击。"""
    registry, backend = _desktop_registry(settings)
    await registry.invoke("screenshot", {})
    result = await registry.invoke("mouse_click", {})
    assert "mouse_move" in result
    assert all(call[0] != "click" for call in backend.calls)


async def test_click_after_move_then_screenshot(settings: Settings) -> None:
    """move 后再 screenshot 仍可点击。"""
    registry, backend = _desktop_registry(settings)
    await registry.invoke("mouse_move", {"x": 10, "y": 10})
    await registry.invoke("screenshot", {})
    result = await registry.invoke("mouse_click", {})
    assert "单击" in _text(result)
    assert any(call[0] == "click" for call in backend.calls)


async def test_second_click_without_move_rejected(settings: Settings) -> None:
    """点完之后未再 mouse_move 则拒绝连点。"""
    registry, backend = _desktop_registry(settings)
    await registry.invoke("mouse_move", {"x": 10, "y": 10})
    first = await registry.invoke("mouse_click", {})
    assert "单击" in _text(first)
    second = await registry.invoke("mouse_click", {})
    assert "mouse_move" in second
    assert [call[0] for call in backend.calls].count("click") == 1


async def test_keyboard_without_screenshot_rejected(settings: Settings) -> None:
    """尚无截图时拒绝键盘输入。"""
    registry, backend = _desktop_registry(settings)
    typed = await registry.invoke("keyboard_type", {"text": "1+1"})
    assert "screenshot" in typed or "mouse_move" in typed
    assert all(call[0] != "write" for call in backend.calls)


async def test_drag_from_current_pointer(settings: Settings) -> None:
    """拖拽从当前位置开始，拒绝 x1/y1。"""
    registry, backend = _desktop_registry(settings)
    shot = await registry.invoke("screenshot", {})
    payload = json.loads(shot.text)
    await registry.invoke("mouse_move", {"x": 8, "y": 8})
    start = backend.mouse
    rejected = await registry.invoke("mouse_drag", {"x1": 1, "y1": 1, "x2": 20, "y2": 20})
    assert isinstance(rejected, ToolResult)
    assert rejected.code == "invalid_arguments"
    assert "未知字段" in rejected
    dragged = await registry.invoke(
        "mouse_drag",
        {"x2": payload["view_width"] // 3, "y2": payload["view_height"] // 3},
    )
    assert "拖到" in _text(dragged)
    drag = next(call for call in backend.calls if call[0] == "drag_to")
    assert drag[1]["x1"] == start[0]
    assert drag[1]["y1"] == start[1]


async def test_oversized_screenshot_region_clamped(settings: Settings) -> None:
    """大于主屏的 region 按主屏夹紧，不把超界宽高写入坐标系。"""
    registry, backend = _desktop_registry(settings)
    backend.screen_size = (1920, 1080)
    result = await registry.invoke(
        "screenshot", {"region": {"x": 0, "y": 0, "width": 2560, "height": 1440}}
    )
    payload = json.loads(_text(result))
    assert payload["width"] == 1920
    assert payload["height"] == 1080
    frame = active_view_frame()
    assert frame is not None
    assert frame.logical_width == 1920
    assert frame.logical_height == 1080


async def test_action_screenshot_covers_stale_oversize_frame(settings: Settings) -> None:
    """后置全屏截图覆盖错误的超界逻辑尺寸。"""
    registry, backend = _desktop_registry(settings)
    await registry.invoke("screenshot", {})
    real = active_view_frame()
    assert real is not None
    store_view_frame(
        ViewFrame(
            origin_x=0,
            origin_y=0,
            logical_width=2560,
            logical_height=1440,
            view_width=real.view_width,
            view_height=real.view_height,
            image_path=real.image_path,
        )
    )
    await registry.invoke("mouse_move", {"x": 8, "y": 8})
    frame = active_view_frame()
    assert frame is not None
    assert frame.logical_width == backend.screen_size[0]
    assert frame.logical_height == backend.screen_size[1]


async def test_session_cache_beats_stale_contextvar(settings: Settings) -> None:
    """父 ContextVar 仍是超界帧时，换算使用会话缓存。"""
    registry, backend = _desktop_registry(settings)
    shot = await registry.invoke("screenshot", {})
    payload = json.loads(_text(shot))
    real = active_view_frame()
    assert real is not None
    current_view_frame.set(
        ViewFrame(
            origin_x=0,
            origin_y=0,
            logical_width=2560,
            logical_height=1440,
            view_width=real.view_width,
            view_height=real.view_height,
            image_path=real.image_path,
        )
    )
    assert active_view_frame() is not None
    assert active_view_frame().logical_height == payload["height"]
    view_y = payload["view_height"] - 1
    expected_y = round(view_y * payload["height"] / payload["view_height"])
    await registry.invoke("mouse_move", {"x": 0, "y": view_y})
    assert backend.mouse[1] == expected_y


async def test_macos_rejects_windows_key(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """darwin 上拒绝 Win+R，提示改用 command。"""
    monkeypatch.setattr("max_gui.tools.desktop.sys.platform", "darwin")
    registry, backend = _desktop_registry(settings)
    await registry.invoke("screenshot", {})
    before = list(backend.calls)
    result = await registry.invoke("keyboard_press", {"keys": ["windows", "r"]})
    assert "macOS" in result
    assert "command" in result
    win = await registry.invoke("keyboard_press", {"keys": ["win", "r"]})
    assert "macOS" in win
    assert backend.calls == before
