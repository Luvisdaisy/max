"""将窗口、截图和 OCR 组合为可比较的标准观察。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from PIL import ImageChops

from max_agent.orchestration.models import (
    ScreenBounds,
    StandardObservation,
    WindowIdentity,
)
from max_agent.orchestration.resources import ResourceRef
from max_agent.tools.base import ToolContext, ToolReceipt
from max_agent.tools.registry import ToolRegistry


class ObservationError(RuntimeError):
    """主观察链路无法产生屏幕证据。"""


class ObservationService:
    """由编排器确定性调度窗口、截图和 OCR；增强工具仍按需调用。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def observe(
        self,
        context: ToolContext,
        previous: StandardObservation | None = None,
        monitor_index: int = 0,
    ) -> tuple[StandardObservation, list[ToolReceipt]]:
        windows = self._registry.invoke("observe_windows", {}, context)
        screen = self._registry.invoke(
            "observe_screen", {"monitor_index": monitor_index}, context
        )
        receipts = [windows, screen]
        if not screen.success:
            raise ObservationError(
                screen.error.message if screen.error else "screen observation failed"
            )
        image_ref = ResourceRef.model_validate(screen.data["image_ref"])
        region, unchanged = _changed_region(context, previous, image_ref, screen.data)
        ocr_payload: dict[str, object] = {"image_ref": image_ref.model_dump()}
        if region is not None:
            ocr_payload["region"] = region.model_dump()
        ocr = (
            ToolReceipt(
                tool_name="recognize_text",
                success=True,
                data={"lines": previous.ocr_lines, "reused": True},
            )
            if unchanged and previous is not None
            else self._registry.invoke("recognize_text", ocr_payload, context)
        )
        receipts.append(ocr)
        ocr_lines = ocr.data.get("lines", []) if ocr.success else []
        if previous is not None and region is not None and ocr.success:
            ocr_lines = [
                *[
                    line
                    for line in previous.ocr_lines
                    if not _intersects(line.get("bounds"), region)
                ],
                *ocr_lines,
            ]
        window_items = windows.data.get("windows", []) if windows.success else []
        foreground_payload = screen.data.get("foreground_window")
        foreground = (
            WindowIdentity.model_validate(foreground_payload)
            if foreground_payload
            else None
        )
        bounds = ScreenBounds.model_validate(screen.data["bounds"])
        fingerprint = observation_fingerprint(window_items, ocr_lines, foreground)
        changed = []
        if region is not None:
            changed = [
                ScreenBounds(
                    left=bounds.left + region.left,
                    top=bounds.top + region.top,
                    width=region.width,
                    height=region.height,
                )
            ]
        elif previous is not None and previous.fingerprint != fingerprint:
            changed = [bounds]
        observation = StandardObservation(
            image_ref=image_ref,
            captured_at=float(screen.data["captured_at"]),
            bounds=bounds,
            dpi=screen.data.get("dpi"),
            foreground_window=foreground,
            windows=window_items,
            ocr_lines=ocr_lines,
            fingerprint=fingerprint,
            changed_regions=changed,
        )
        return observation, receipts


def observation_fingerprint(
    windows: list[dict[str, Any]],
    ocr_lines: list[dict[str, Any]],
    foreground: WindowIdentity | None,
) -> str:
    """只对稳定结构证据计算指纹，避免把原始图像写入状态。"""
    payload = {
        "foreground": foreground.model_dump(exclude={"title"}) if foreground else None,
        "windows": [
            {
                key: item.get(key)
                for key in (
                    "hwnd",
                    "process_id",
                    "executable_path",
                    "bounds",
                    "foreground",
                )
            }
            for item in windows
        ],
        "ocr": [
            {
                "text_hash": hashlib.sha256(
                    str(item.get("text", "")).encode()
                ).hexdigest(),
                "bounds": item.get("bounds"),
            }
            for item in ocr_lines
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _changed_region(
    context: ToolContext,
    previous: StandardObservation | None,
    current_ref: ResourceRef,
    screen: dict[str, Any],
) -> tuple[ScreenBounds | None, bool]:
    """显示拓扑稳定时计算像素差异包围框，未变化帧直接复用 OCR。"""
    if previous is None:
        return None, False
    current = ScreenBounds.model_validate(screen["bounds"])
    if previous.bounds != current or previous.dpi != screen.get("dpi"):
        return None, False
    try:
        before = context.resources.get(
            ResourceRef.model_validate(previous.image_ref), context.task_id, "image"
        )
        after = context.resources.get(current_ref, context.task_id, "image")
    except Exception:
        return None, False
    if before.size != after.size:
        return None, False
    bbox = ImageChops.difference(before.convert("RGB"), after.convert("RGB")).getbbox()
    if bbox is None:
        return None, True
    left, top, right, bottom = bbox
    # 像素差分通常只包住字形本身；OCR 检测器需要少量周边背景才能稳定
    # 找到文本行。留白仍限制在当前截图内，不会扩大到其他显示器或重截图。
    padding = 24
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(current.width, right + padding)
    bottom = min(current.height, bottom + padding)
    return ScreenBounds(
        left=left, top=top, width=max(1, right - left), height=max(1, bottom - top)
    ), False


def _intersects(raw_bounds: Any, region: ScreenBounds) -> bool:
    if isinstance(raw_bounds, dict):
        try:
            bounds = ScreenBounds.model_validate(raw_bounds)
        except Exception:
            return True
        return not (
            bounds.left + bounds.width <= region.left
            or region.left + region.width <= bounds.left
            or bounds.top + bounds.height <= region.top
            or region.top + region.height <= bounds.top
        )
    return True
