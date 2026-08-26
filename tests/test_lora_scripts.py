"""LoRA 训练与评估脚本的离线契约测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _load(name: str, filename: str):
    """从 scripts 加载可测试模块，不要求把脚本变成安装包。"""
    path = Path(__file__).resolve().parents[1] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


train = _load("train_lora", "train_lora.py")
evaluate = _load("eval_lora", "eval_lora.py")


def test_canonical_target_preserves_strict_keyboard_array() -> None:
    """act 标签保留当前工具协议规定的 keys 数组格式。"""
    target = train.canonical_target(
        {
            "stage": "act",
            "actions": [{"tool": "keyboard_press", "args": {"keys": ["command", "tab"]}}],
        }
    )
    assert json.loads(target) == [{"tool": "keyboard_press", "args": {"keys": ["command", "tab"]}}]


def test_lora_defaults_match_change_design() -> None:
    """LoRA 默认 rank、alpha 与目标层和设计文档一致。"""
    arguments = train.LoraArguments()
    assert (arguments.rank, arguments.alpha, arguments.dropout) == (64, 32, 0.05)
    assert arguments.max_length == 2048
    assert arguments.max_pixels == 1024 * 768
    assert train.LORA_TARGET_MODULES == (
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    )


def test_eval_score_reports_format_and_exact_action_rates() -> None:
    """评估同时区分合法 JSON 与和标注完全一致的动作。"""
    records = [
        {"stage": "act", "actions": [{"tool": "mouse_click", "args": {"x": 1, "y": 2}}]},
        {"stage": "act", "actions": [{"tool": "keyboard_type", "args": {"text": "x"}}]},
    ]
    report = evaluate.score(records, ['[{"tool":"mouse_click","args":{"x":1,"y":2}}]', "not json"])
    assert report == {"samples": 2, "valid_json_rate": 0.5, "exact_action_rate": 0.5}
