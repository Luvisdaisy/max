"""把本地图像压成发给多模态接口的 JPEG data URL，并报告编码后尺寸。"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


class ImagePrepError(ValueError):
    """文件不存在、后缀不支持或无法按图像打开。"""


SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


@dataclass(frozen=True, slots=True)
class PreparedImage:
    """预处理结果。

    字段：
        part: OpenAI `image_url` 内容部件。
        width / height: 实际发给模型的 JPEG 像素尺寸。
    """

    part: dict[str, Any]
    width: int
    height: int


def fit_rgb_image(
    image: Image.Image, *, max_edge: int, max_bytes: int
) -> tuple[Image.Image, bytes]:
    """按最长边与字节上限缩小并编码为 JPEG。

    参数：
        image: RGB 或可转 RGB 的图。
        max_edge: 最长边像素上限。
        max_bytes: JPEG 字节上限。

    返回：
        `(拟合后的 RGB 图, JPEG 字节)`。
    """
    converted = image.convert("RGB") if image.mode not in {"RGB", "L"} else image.copy()
    width, height = converted.size
    longest = max(width, height)
    if longest > max_edge:
        scale = max_edge / float(longest)
        converted = converted.resize(
            (max(1, int(width * scale)), max(1, int(height * scale))),
            Image.Resampling.LANCZOS,
        )

    quality = 90
    raw = _encode(converted, quality=quality)
    while len(raw) > max_bytes and quality > 40:
        quality -= 10
        raw = _encode(converted, quality=quality)
    if len(raw) > max_bytes:
        width, height = converted.size
        converted = converted.resize(
            (max(1, width // 2), max(1, height // 2)), Image.Resampling.LANCZOS
        )
        raw = _encode(converted, quality=70)
    return converted, raw


def prepare_image(
    path: Path,
    *,
    max_edge: int,
    max_bytes: int,
) -> PreparedImage:
    """读取图像，限制最长边与编码体积，返回 data URL 与编码后宽高。

    先按 `max_edge` 等比缩小，再降低 JPEG 质量；仍超限则边长再减半。

    参数：
        path: 本地图像路径。
        max_edge: 最长边像素上限。
        max_bytes: JPEG 字节上限。

    返回：
        含 `image_url` 部件与编码后宽高的 `PreparedImage`。

    异常：
        ImagePrepError: 路径无效或不是图像。
    """
    source = Path(path)
    if not source.is_file():
        raise ImagePrepError(f"图像不存在：{source}")
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ImagePrepError(f"不支持的图像类型：{source.suffix or source.name}")

    try:
        with Image.open(source) as image:
            image.load()
            converted = image.convert("RGB") if image.mode not in {"RGB", "L"} else image.copy()
    except UnidentifiedImageError as exc:
        raise ImagePrepError(f"不是有效图像：{source}") from exc

    fitted, raw = fit_rgb_image(converted, max_edge=max_edge, max_bytes=max_bytes)
    b64 = base64.b64encode(raw).decode("ascii")
    return PreparedImage(
        part={
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        },
        width=fitted.width,
        height=fitted.height,
    )


def _encode(image: Image.Image, *, quality: int) -> bytes:
    """把 PIL 图像编码为优化 JPEG 字节。"""
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()
