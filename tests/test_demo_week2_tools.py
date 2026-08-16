"""第二周演示脚本：只测计算器布局换算，不启动系统应用。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "demo_week2_tools.py"
_SPEC = importlib.util.spec_from_file_location("demo_week2_tools", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
demo = importlib.util.module_from_spec(_SPEC)
sys.modules["demo_week2_tools"] = demo
_SPEC.loader.exec_module(demo)


def _assert_inside(window: demo.WindowBox, layout: dict) -> None:
    """所有矩形及其中心都落在窗口内。"""
    for box in layout.values():
        assert box.x >= window.x
        assert box.y >= window.y
        assert box.x + box.w <= window.x + window.w
        assert box.y + box.h <= window.y + window.h
        assert window.x <= box.cx < window.x + window.w
        assert window.y <= box.cy < window.y + window.h


def test_narrow_layout_uses_four_equal_bottom_keys() -> None:
    """窄窗口无历史栏；底行四键等宽，顶行是 ``AC`` 不是 ``C``。"""
    window = demo.WindowBox(x=100, y=80, w=240, h=400)
    assert not window.has_sidebar
    layout = demo.calculator_layout(window)

    assert "sidebar" not in layout
    assert "AC" in layout
    assert "C" not in layout
    display = layout["display"]
    assert display.cy < layout["AC"].cy
    assert layout["AC"].x > display.x

    zero = layout["0"]
    one = layout["1"]
    equals = layout["="]
    plus_minus = layout["+/-"]
    assert zero.w == one.w
    assert plus_minus.x >= window.x
    assert equals.x + equals.w <= window.x + window.w
    assert equals.y == zero.y
    assert layout["drag"].cy < layout["AC"].cy
    _assert_inside(window, layout)


def test_wide_layout_puts_keypad_right_of_history() -> None:
    """宽窗口把历史栏放在左侧，按键与拖拽空白在右侧。"""
    window = demo.WindowBox(x=40, y=50, w=500, h=400)
    assert window.has_sidebar
    layout = demo.calculator_layout(window)

    sidebar = layout["sidebar"]
    history = layout["history"]
    drag = layout["drag"]
    one = layout["1"]
    assert sidebar.x == window.x
    assert sidebar.w < window.w
    assert history.cx < one.cx
    assert drag.x >= sidebar.x + sidebar.w
    assert one.x >= sidebar.x + sidebar.w
    assert layout["="].x + layout["="].w <= window.x + window.w
    _assert_inside(window, layout)


def test_measured_wide_window_places_one_and_four_on_right_pane() -> None:
    """对照 458×408 实测：1/4 中心约 (611, …)，不再落在侧栏缝里。"""
    window = demo.WindowBox(x=349, y=370, w=458, h=408)
    layout = demo.calculator_layout(window)
    assert abs(layout["1"].cx - 611) <= 2
    assert abs(layout["4"].cx - 611) <= 2
    assert abs(layout["1"].cy - 689) <= 3
    assert layout["1"].w <= 52
    assert layout["7"].x > window.x + window.w * 0.45


def test_parse_ax_report_maps_button_order() -> None:
    """辅助功能行协议按 1–20 对上按键名。"""
    raw = "BTN|587|665|48|48|13\nHIST|357|422|220|348\n"
    parsed = demo.parse_ax_report(raw)
    assert parsed["1"] == demo.Rect("1", 587, 665, 48, 48)
    assert parsed["history"].w == 220


def test_format_ocr_text_strips_latex() -> None:
    """OCR 原文里的数学定界符收成普通乘号行。"""
    raw = "今天\n\\(5 \\times 6\\)\n30\n"
    assert demo.format_ocr_text(raw) == "今天\n5 × 6\n30"


def test_region_matches_window() -> None:
    """区域截图参数与外框一致。"""
    window = demo.WindowBox(x=40, y=60, w=200, h=300)
    assert window.region == {"x": 40, "y": 60, "width": 200, "height": 300}
