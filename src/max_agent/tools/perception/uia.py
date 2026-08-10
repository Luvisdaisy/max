"""UI Automation 观察工具：读取指定进程元素，不激活或操控窗口。"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from max_agent.tools.base import ToolFailureCode, ToolReceipt


class ObserveUiElementsInput(BaseModel):
    process_id: int = Field(gt=0)
    max_elements: int = Field(default=100, ge=1, le=500)


class ObserveUiElementsTool:
    """限制元素数量并将原生 UIA 结果转换为普通数据。"""

    name = "observe_ui_elements"
    input_model = ObserveUiElementsInput

    def __init__(
        self, observer: Callable[[int, int], list[dict[str, object]]] | None = None
    ) -> None:
        self._observer = observer or _observe_process

    def invoke(self, tool_input: ObserveUiElementsInput) -> ToolReceipt:
        try:
            elements = self._observer(tool_input.process_id, tool_input.max_elements)
        except Exception as error:  # inaccessible UIA targets are observation failures
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.UNAVAILABLE,
                f"{type(error).__name__}: {error}",
            )
        return ToolReceipt(
            tool_name=self.name, success=True, data={"elements": elements}
        )


def _observe_process(process_id: int, max_elements: int) -> list[dict[str, object]]:
    from pywinauto import Application

    window = Application(backend="uia").connect(process=process_id).top_window()
    elements: list[dict[str, object]] = []
    for element in window.descendants()[:max_elements]:
        info = element.element_info
        rectangle = element.rectangle()
        elements.append(
            {
                "name": info.name or "",
                "role": info.control_type or "",
                "bounds": {
                    "left": rectangle.left,
                    "top": rectangle.top,
                    "width": rectangle.width(),
                    "height": rectangle.height(),
                },
                "enabled": bool(element.is_enabled()),
            }
        )
    return elements
