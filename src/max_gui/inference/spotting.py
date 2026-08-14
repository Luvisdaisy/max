"""解析 PaddleOCR-VL `Spotting:` 文本为轴对齐框。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


class SpottingParseError(ValueError):
    """模型输出里解析不出任何框。"""


@dataclass(frozen=True, slots=True)
class SpotBox:
    """一条文字行框，坐标在 spotting 输入图像素上。

    字段：
        text: 识别文本。
        x1 / y1 / x2 / y2: 左上与右下。
    """

    text: str
    x1: float
    y1: float
    x2: float
    y2: float


_QUAD_LINE = re.compile(r"^(?P<text>.*?)\s*(?P<quad>\[\[[^\]]+\](?:\s*,\s*\[[^\]]+\]){3}\])\s*$")
_BBOX_LINE = re.compile(
    r"^(?P<text>.*?)\s*[\[(](?P<x1>-?[\d.]+)\s*,\s*(?P<y1>-?[\d.]+)\s*,\s*"
    r"(?P<x2>-?[\d.]+)\s*,\s*(?P<y2>-?[\d.]+)[\])]\s*$"
)
_NUM = re.compile(r"-?[\d.]+")


def parse_spotting(text: str) -> list[SpotBox]:
    """从 spotting 原文抽出文字行框。

    依次尝试整段 JSON、制表符四边形、以及行末 `[x1, y1, x2, y2]`。

    参数：
        text: 模型返回的原始字符串。

    返回：
        至少一个 `SpotBox`。

    异常：
        SpottingParseError: 一个框都解析不出来。
    """
    raw = (text or "").strip()
    if not raw:
        raise SpottingParseError("空定位结果")
    boxes = _from_json(raw)
    if not boxes:
        boxes = _from_lines(raw)
    if not boxes:
        raise SpottingParseError("无法解析文字定位结果")
    return boxes


def _from_json(raw: str) -> list[SpotBox]:
    """若整段是 JSON 数组或对象，抽出框。"""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        for key in ("items", "boxes", "result", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
        else:
            items = [payload]
    else:
        return []
    boxes: list[SpotBox] = []
    for item in items:
        parsed = _from_mapping(item) if isinstance(item, dict) else _from_sequence(item)
        if parsed is not None:
            boxes.append(parsed)
    return boxes


def _from_mapping(item: dict[str, Any]) -> SpotBox | None:
    """从常见字段名取文本与框。"""
    text = str(item.get("text") or item.get("transcription") or item.get("label") or "").strip()
    for key in ("bbox", "box", "rect"):
        if key in item:
            box = _numbers_to_box(item[key], text)
            if box is not None:
                return box
    if "points" in item:
        return _numbers_to_box(item["points"], text)
    if "x1" in item and "y1" in item and "x2" in item and "y2" in item:
        return SpotBox(
            text=text,
            x1=float(item["x1"]),
            y1=float(item["y1"]),
            x2=float(item["x2"]),
            y2=float(item["y2"]),
        )
    return None


def _from_sequence(item: Any) -> SpotBox | None:
    """`[text, bbox]` 或纯数字列表。"""
    if not isinstance(item, list) or not item:
        return None
    if isinstance(item[0], str) and len(item) >= 2:
        return _numbers_to_box(item[1], item[0])
    return _numbers_to_box(item, "")


def _from_lines(raw: str) -> list[SpotBox]:
    """按行解析四边形或轴对齐框。"""
    boxes: list[SpotBox] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _QUAD_LINE.match(stripped)
        if match:
            box = _numbers_to_box(match.group("quad"), match.group("text").strip(" \t:|-"))
            if box is not None:
                boxes.append(box)
                continue
        match = _BBOX_LINE.match(stripped)
        if match:
            text = match.group("text").strip(" \t:|-")
            boxes.append(
                SpotBox(
                    text=text,
                    x1=float(match.group("x1")),
                    y1=float(match.group("y1")),
                    x2=float(match.group("x2")),
                    y2=float(match.group("y2")),
                )
            )
    return boxes


def _numbers_to_box(value: Any, text: str) -> SpotBox | None:
    """把四边形、`[x1,y1,x2,y2]` 或嵌套点列收成轴对齐框。"""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            nums = [float(item) for item in _NUM.findall(value)]
            return _floats_to_box(nums, text)
    nums = _flatten_numbers(value)
    return _floats_to_box(nums, text)


def _flatten_numbers(value: Any) -> list[float]:
    """递归抽出数字。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [float(value)]
    if isinstance(value, (list, tuple)):
        out: list[float] = []
        for item in value:
            out.extend(_flatten_numbers(item))
        return out
    return []


def _floats_to_box(nums: list[float], text: str) -> SpotBox | None:
    """4 个数当轴对齐框；8 个数当四边形取外接矩形。"""
    if len(nums) == 4:
        x1, y1, x2, y2 = nums
        return SpotBox(text=text, x1=min(x1, x2), y1=min(y1, y2), x2=max(x1, x2), y2=max(y1, y2))
    if len(nums) >= 8:
        xs = nums[0::2][:4]
        ys = nums[1::2][:4]
        return SpotBox(text=text, x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys))
    return None
