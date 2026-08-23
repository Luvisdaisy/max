"""OmniParser worker：独立进程加载检测权重，提供 `/health` 与 `/parse`。

在 vLLM 旁的解释器中运行，避免把 torch 打进项目 `.venv`。
YOLO 必须能加载；Florence caption 与 EasyOCR 失败时仍返回检测框。
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def main(argv: list[str] | None = None) -> int:
    """解析参数、加载模型并监听 HTTP。

    参数：
        argv: 命令行；缺省用 `sys.argv[1:]`。

    返回：
        进程退出码。
    """
    parser = argparse.ArgumentParser(description="OmniParser locate worker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--weights", required=True)
    args = parser.parse_args(argv)
    weights = Path(args.weights)
    try:
        engine = OmniParserEngine(weights)
    except Exception as exc:
        print(f"failed to load OmniParser: {exc}", file=sys.stderr)
        return 1

    class Handler(BaseHTTPRequestHandler):
        """健康检查与解析。"""

        def log_message(self, format: str, *args: object) -> None:
            """不把访问日志打到 stderr，避免污染父进程。"""
            return

        def do_GET(self) -> None:
            """`/health` 在模型已加载时返回 200。"""
            if self.path.split("?", 1)[0] != "/health":
                self._send(404, {"error": "not found"})
                return
            self._send(200, {"ok": True})

        def do_POST(self) -> None:
            """`/parse` 读取 JSON `path` 并返回框列表。"""
            if self.path.split("?", 1)[0] != "/parse":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self._send(400, {"error": "invalid json"})
                return
            path = Path(str(payload.get("path") or ""))
            if not path.is_file():
                self._send(400, {"error": f"missing image: {path}"})
                return
            try:
                boxes = engine.parse(path)
            except Exception as exc:
                self._send(500, {"error": str(exc)})
                return
            self._send(200, {"boxes": boxes})

        def _send(self, code: int, body: dict[str, Any]) -> None:
            """写 JSON 响应。"""
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.serve_forever()
    return 0


class OmniParserEngine:
    """加载 YOLO 检测，并尽力附加 OCR 标签与 Florence caption。"""

    def __init__(self, weights: Path) -> None:
        """参数：`weights` 为 `model/omniparserv2` 一类目录。"""
        self.weights = weights
        detect_path = _find_detect_weights(weights)
        if detect_path is None:
            raise FileNotFoundError(f"未找到 icon_detect 权重：{weights}")
        from ultralytics import YOLO

        self.detector = YOLO(str(detect_path))
        self._ocr: Any = None
        self._ocr_tried = False
        self._caption: _FlorenceCaptioner | None = None
        self._caption_tried = False
        print(f"YOLO ready: {detect_path}", file=sys.stderr, flush=True)

    def parse(self, path: Path) -> list[dict[str, Any]]:
        """对一张图做检测，返回可 JSON 序列化的框。

        参数：
            path: 本地图像。

        返回：
            每项含 `x1,y1,x2,y2,label,role,score,normalized`。
        """
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
        results = self.detector.predict(source=str(path), verbose=False, conf=0.05)
        if not results:
            return []
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None or boxes.xyxyn is None:
            return []
        ocr_items = self._ocr_items(path) if self._ensure_ocr() is not None else []
        parsed: list[dict[str, Any]] = []
        xyxyn = boxes.xyxyn.cpu().tolist()
        confs = boxes.conf.cpu().tolist() if boxes.conf is not None else [0.0] * len(xyxyn)
        for coords, score in zip(xyxyn, confs, strict=False):
            x1, y1, x2, y2 = (
                float(coords[0]),
                float(coords[1]),
                float(coords[2]),
                float(coords[3]),
            )
            label = _label_from_ocr(ocr_items, x1, y1, x2, y2)
            role = "text" if label else "icon"
            if not label and self._ensure_caption() is not None:
                try:
                    label = self._caption.caption(path, x1, y1, x2, y2, width, height)
                except Exception:
                    label = ""
            if not label:
                label = role
            parsed.append(
                {
                    "x1": x1,
                    "y1": y1,
                    "x2": x2,
                    "y2": y2,
                    "label": label,
                    "role": role,
                    "score": float(score),
                    "normalized": True,
                }
            )
        return parsed

    def _ensure_ocr(self) -> Any:
        """第一次解析再尝试 EasyOCR，失败则永久跳过。"""
        if not self._ocr_tried:
            self._ocr_tried = True
            self._ocr = _try_easyocr()
        return self._ocr

    def _ensure_caption(self) -> _FlorenceCaptioner | None:
        """第一次解析再尝试 Florence，失败则永久跳过。"""
        if not self._caption_tried:
            self._caption_tried = True
            self._caption = _try_florence(self.weights)
        return self._caption

    def _ocr_items(self, path: Path) -> list[tuple[float, float, float, float, str]]:
        """EasyOCR 结果转成归一化框加文本。"""
        if self._ocr is None:
            return []
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
        items: list[tuple[float, float, float, float, str]] = []
        for box, text, _conf in self._ocr.readtext(str(path)):
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            if not xs or not ys:
                continue
            label = str(text or "").strip()
            if not label:
                continue
            items.append(
                (
                    min(xs) / width,
                    min(ys) / height,
                    max(xs) / width,
                    max(ys) / height,
                    label,
                )
            )
        return items


class _FlorenceCaptioner:
    """可选的 Florence-2 图标描述；加载失败则不要构造本对象。"""

    def __init__(self, model_dir: Path) -> None:
        """参数：`model_dir` 为 `icon_caption` 或 `icon_caption_florence` 目录。"""
        import torch
        from transformers import AutoModelForCausalLM, AutoProcessor

        self.device = "cpu"
        self.processor = AutoProcessor.from_pretrained(str(model_dir), trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            str(model_dir), trust_remote_code=True, torch_dtype=torch.float32
        ).to(self.device)

    def caption(
        self,
        path: Path,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        width: int,
        height: int,
    ) -> str:
        """对归一化框裁一块图做短描述。"""
        from PIL import Image

        with Image.open(path) as image:
            crop = image.convert("RGB").crop(
                (
                    int(x1 * width),
                    int(y1 * height),
                    int(x2 * width),
                    int(y2 * height),
                )
            )
        if crop.width < 2 or crop.height < 2:
            return ""
        prompt = "<CAPTION>"
        inputs = self.processor(text=prompt, images=crop, return_tensors="pt")
        generated = self.model.generate(**inputs, max_new_tokens=20)
        text = self.processor.batch_decode(generated, skip_special_tokens=True)[0]
        return str(text or "").replace(prompt, "").strip()


def _find_detect_weights(root: Path) -> Path | None:
    """在常见 OmniParser 布局里找 YOLO 权重。"""
    candidates = [
        root / "icon_detect" / "model.pt",
        root / "icon_detect" / "best.pt",
        root / "icon_detect.pt",
        root / "model.pt",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _try_easyocr() -> Any:
    """能 import 则构造 Reader；失败返回 `None`。"""
    try:
        import easyocr

        return easyocr.Reader(["ch_sim", "en"], verbose=False)
    except Exception:
        return None


def _try_florence(weights: Path) -> _FlorenceCaptioner | None:
    """caption 权重存在且能加载则返回描述器。"""
    for name in ("icon_caption", "icon_caption_florence"):
        directory = weights / name
        if not directory.is_dir():
            continue
        try:
            return _FlorenceCaptioner(directory)
        except Exception:
            continue
    return None


def _label_from_ocr(
    items: list[tuple[float, float, float, float, str]],
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> str:
    """取与检测框 IoU 最高且超过阈值的 OCR 文本。"""
    best = ""
    best_iou = 0.15
    for ox1, oy1, ox2, oy2, text in items:
        iou = _iou(x1, y1, x2, y2, ox1, oy1, ox2, oy2)
        if iou > best_iou:
            best_iou = iou
            best = text
    return best


def _iou(
    ax1: float,
    ay1: float,
    ax2: float,
    ay2: float,
    bx1: float,
    by1: float,
    bx2: float,
    by2: float,
) -> float:
    """两个轴对齐框的交并比。"""
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


if __name__ == "__main__":
    raise SystemExit(main())
