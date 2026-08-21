"""ScreenAgent 预处理脚本：动作映射、负例过滤与 JSONL 写出。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_screenagent.py"
_SPEC = importlib.util.spec_from_file_location("prepare_screenagent", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
prep = importlib.util.module_from_spec(_SPEC)
sys.modules["prepare_screenagent"] = prep
_SPEC.loader.exec_module(prep)


def _write_jpg(path: Path) -> None:
    """写一个最小 JPEG 头，只要求文件存在。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8\xff\xd9")


def _session(root: Path, split: str, session_id: str) -> Path:
    """构造 session 目录。"""
    session = root / split / session_id
    (session / "images").mkdir(parents=True)
    return session


def test_map_click_and_keys() -> None:
    """点击坐标取 width/height；Ctrl+S 收到 keyboard_press。"""
    stats = prep.ConvertStats()
    mapped, plan, skips = prep.map_actions(
        [
            {
                "action_type": "MouseAction",
                "mouse_action_type": "click",
                "mouse_button": "left",
                "mouse_position": {"width": 368, "height": 319},
            },
            {
                "action_type": "KeyboardAction",
                "keyboard_action_type": "press",
                "keyboard_key": ["Control_L", "s"],
            },
        ],
        1024,
        768,
        stats,
    )
    assert plan == []
    assert skips == []
    assert mapped == [
        {
            "tool": "mouse_click",
            "args": {"x": 368, "y": 319, "button": "left", "clicks": 1},
        },
        {"tool": "keyboard_press", "args": {"keys": ["ctrl", "s"]}},
    ]


def test_down_up_merges_to_drag() -> None:
    """同一步的 down+up 合成带起点终点的 mouse_drag。"""
    stats = prep.ConvertStats()
    mapped, _, skips = prep.map_actions(
        [
            {
                "action_type": "MouseAction",
                "mouse_action_type": "down",
                "mouse_button": "left",
                "mouse_position": {"width": 50, "height": 578},
            },
            {
                "action_type": "MouseAction",
                "mouse_action_type": "up",
                "mouse_button": "left",
                "mouse_position": {"width": 408, "height": 584},
            },
        ],
        1024,
        768,
        stats,
    )
    assert skips == []
    assert mapped == [
        {
            "tool": "mouse_drag",
            "args": {"x1": 50, "y1": 578, "x2": 408, "y2": 584, "button": "left"},
        }
    ]


def test_out_of_view_is_skipped() -> None:
    """出界坐标不夹到边上，动作丢弃。"""
    stats = prep.ConvertStats()
    mapped, _, skips = prep.map_actions(
        [
            {
                "action_type": "MouseAction",
                "mouse_action_type": "click",
                "mouse_button": "left",
                "mouse_position": {"width": 2000, "height": 10},
            }
        ],
        1024,
        768,
        stats,
    )
    assert mapped == []
    assert "mouse_out_of_view" in skips


def test_convert_split_skips_negatives(tmp_path: Path) -> None:
    """负例 JSON 不进 JSONL；缺图样本记入统计。"""
    session = _session(tmp_path, "train", "abc")
    image = session / "images" / "ok.jpg"
    _write_jpg(image)
    positive = {
        "task_prompt_zh": "上网查找资料",
        "session_id": "abc",
        "video_width": 1024,
        "video_height": 768,
        "saved_image_name": "ok.jpg",
        "current_task": "打开浏览器",
        "LLM_response_editer_zh": "计划文本",
        "actions": [{"action_type": "PlanAction", "element": "打开浏览器"}],
    }
    (session / "t_translate.json").write_text(json.dumps(positive), encoding="utf-8")
    (session / "t_translate_neg_plan.json").write_text(json.dumps(positive), encoding="utf-8")
    missing = dict(positive)
    missing["saved_image_name"] = "gone.jpg"
    (session / "missing_translate.json").write_text(json.dumps(missing), encoding="utf-8")

    test_session = _session(tmp_path, "test", "xyz")
    _write_jpg(test_session / "images" / "t.jpg")
    test_record = {
        "task_prompt": "Change font",
        "session_id": "xyz",
        "video_width": 1024,
        "video_height": 768,
        "saved_image_name": "t.jpg",
        "current_task": "Click Enter",
        "LLM_response_editer": "click",
        "actions": [
            {
                "action_type": "MouseAction",
                "mouse_action_type": "double_click",
                "mouse_button": "left",
                "mouse_position": {"width": 10, "height": 20},
            }
        ],
    }
    (test_session / "2024.json").write_text(json.dumps(test_record), encoding="utf-8")
    (test_session / "2024_neg_eval.json").write_text(json.dumps(test_record), encoding="utf-8")

    stats = prep.ConvertStats()
    train = prep.convert_split(tmp_path, "train", tmp_path, stats)
    test = prep.convert_split(tmp_path, "test", tmp_path, stats)
    assert len(train) == 1
    assert train[0]["stage"] == "plan"
    assert train[0]["plan"] == ["打开浏览器"]
    assert train[0]["image"] == "train/abc/images/ok.jpg"
    assert len(test) == 1
    assert test[0]["actions"][0]["args"]["clicks"] == 2
    assert stats.skipped_neg == 2
    assert stats.skipped["missing_image"] == 1


def test_cli_writes_jsonl(tmp_path: Path) -> None:
    """命令行在 processed 下写出 train/test JSONL 与统计。"""
    session = _session(tmp_path, "train", "s1")
    _write_jpg(session / "images" / "a.jpg")
    (session / "a_translate.json").write_text(
        json.dumps(
            {
                "task_prompt_zh": "搜索",
                "session_id": "s1",
                "video_width": 1024,
                "video_height": 768,
                "saved_image_name": "a.jpg",
                "LLM_response_editer_zh": "点一下",
                "actions": [
                    {
                        "action_type": "MouseAction",
                        "mouse_action_type": "scroll_down",
                        "scroll_repeat": 3,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    test_session = _session(tmp_path, "test", "s2")
    _write_jpg(test_session / "images" / "b.jpg")
    (test_session / "b.json").write_text(
        json.dumps(
            {
                "task_prompt": "Open files",
                "session_id": "s2",
                "video_width": 1024,
                "video_height": 768,
                "saved_image_name": "b.jpg",
                "LLM_response_editer": "type",
                "actions": [
                    {
                        "action_type": "KeyboardAction",
                        "keyboard_action_type": "text",
                        "keyboard_text": "hello",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "processed"
    assert (
        prep.main(["--raw", str(tmp_path), "--out", str(out), "--project-root", str(tmp_path)]) == 0
    )
    train_lines = (out / "train.jsonl").read_text(encoding="utf-8").strip().splitlines()
    test_lines = (out / "test.jsonl").read_text(encoding="utf-8").strip().splitlines()
    train_row = json.loads(train_lines[0])
    test_row = json.loads(test_lines[0])
    assert train_row["actions"][0] == {"tool": "mouse_scroll", "args": {"clicks": -3}}
    assert test_row["actions"][0] == {"tool": "keyboard_type", "args": {"text": "hello"}}
    assert (out / "stats.md").is_file()
