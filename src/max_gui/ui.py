"""短生命周期 UI 快照与注册表。

本模块只保存当前进程的后端 locator；会话层只能持久化脱敏摘要。元素编号只在
对应 `UISnapshot.version` 有效，观察刷新后必须重新解析，绝不跨帧复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

UIBackendName = Literal["macos_ax", "vision"]
UIContext = Literal["native", "vision"]


class StaleUIError(RuntimeError):
    """元素不存在或所属快照已过期，调用方必须重新观察。"""


@dataclass(frozen=True, slots=True)
class UIElement:
    """单一观察快照内的语义元素。

    参数：`locator` 仅在进程内由后端解析，禁止写入模型上下文或会话 JSON。
    """

    id: str
    role: str
    name: str | None
    text: str | None
    visible: bool
    enabled: bool
    editable: bool
    focused: bool
    app_id: str | None
    window_id: str | None
    backend: UIBackendName
    locator: Any = field(repr=False, compare=False, default=None)
    bbox: tuple[float, float, float, float] | None = None

    def summary(self) -> dict[str, Any]:
        """返回可注入模型和会话的脱敏摘要，不包含 locator 与坐标。"""
        return {
            "id": self.id,
            "role": self.role[:60],
            "label": (self.name or self.text or self.role)[:120],
            "clickable": self.enabled and self.role not in {"text", "static_text"},
            "editable": self.editable,
            "focused": self.focused,
            "backend": self.backend,
        }


@dataclass(frozen=True, slots=True)
class UISnapshot:
    """一次观察的有限元素集合及其时效边界。"""

    version: int
    frame_path: str
    context: UIContext
    elements: tuple[UIElement, ...]
    url: str | None = None

    def summary(self) -> dict[str, Any]:
        """返回不含 locator、边界与完整 URL 的持久化摘要。"""
        return {
            "version": self.version,
            "frame_path": self.frame_path,
            "context": self.context,
            "url": self.url[:200] if self.url else None,
            "elements": [item.summary() for item in self.elements],
        }


class UIRegistry:
    """维护进程内唯一当前快照，并拒绝任何过期元素引用。"""

    def __init__(self) -> None:
        """创建空注册表；版本从 1 开始单调递增。"""
        self._version = 0
        self._current: UISnapshot | None = None

    @property
    def current(self) -> UISnapshot | None:
        """返回当前快照；未观察时返回空。"""
        return self._current

    def replace(
        self,
        *,
        frame_path: str,
        context: UIContext,
        elements: list[UIElement],
        url: str | None = None,
    ) -> UISnapshot:
        """创建新版本快照并作废所有旧元素。

        参数：元素 ID 会按当前观察重新编号为 `e_1` 起的短期标识。
        返回：新建的当前快照。
        """
        self._version += 1
        rebuilt = tuple(
            UIElement(
                id=f"e_{index}",
                role=item.role,
                name=item.name,
                text=item.text,
                visible=item.visible,
                enabled=item.enabled,
                editable=item.editable,
                focused=item.focused,
                app_id=item.app_id,
                window_id=item.window_id,
                backend=item.backend,
                locator=item.locator,
                bbox=item.bbox,
            )
            for index, item in enumerate(elements[:80], start=1)
        )
        self._current = UISnapshot(self._version, str(frame_path), context, rebuilt, url)
        return self._current

    def clear(self) -> None:
        """作废当前快照；新任务、恢复到不同帧和观察失败时调用。"""
        self._current = None

    def resolve(self, *, element_id: str, version: int) -> UIElement:
        """解析当前版本内的元素。

        异常：没有快照、版本不同或元素不存在时抛出 `StaleUIError`，调用方不得分派动作。
        """
        current = self._current
        if current is None or current.version != version:
            raise StaleUIError("UI 快照已过期，请先重新观察界面")
        for item in current.elements:
            if item.id == element_id:
                return item
        raise StaleUIError("当前 UI 快照中不存在该元素，请先重新观察界面")
