from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError


class ImagePrepError(ValueError):
    pass


SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def prepare_image(
    path: Path,
    *,
    max_edge: int,
    max_bytes: int,
) -> dict[str, str]:
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
        # 再缩小一档边长
        width, height = converted.size
        converted = converted.resize((max(1, width // 2), max(1, height // 2)), Image.Resampling.LANCZOS)
        raw = _encode(converted, quality=70)

    b64 = base64.b64encode(raw).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
    }


def _encode(image: Image.Image, *, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()
