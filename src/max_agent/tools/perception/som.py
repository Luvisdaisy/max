"""Set-of-Mark 工具：只处理任务内图像并返回新的资源引用。"""

from __future__ import annotations

from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict, Field, model_validator

from max_agent.orchestration.resources import ResourceError, ResourceRef
from max_agent.tools.base import (
    ToolContext,
    ToolFailureCode,
    ToolPermission,
    ToolPhase,
    ToolReceipt,
)


class SomMark(BaseModel):
    label: str = Field(min_length=1)
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class AnnotateSomInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image_ref: ResourceRef | None = None
    image: Image.Image | None = None
    marks: list[SomMark]

    @model_validator(mode="after")
    def require_source(self) -> "AnnotateSomInput":
        if (self.image_ref is None) == (self.image is None):
            raise ValueError("provide exactly one image_ref or image")
        return self


class AnnotateSomTool:
    name = "annotate_som"
    description = "Annotate candidate regions in a task image."
    permission = ToolPermission.OBSERVE
    allowed_phases = frozenset({ToolPhase.TOOL})
    timeout_seconds = 15.0
    recoverable = True
    model_visible = True
    side_effect = False
    read_only = True
    input_model = AnnotateSomInput

    def invoke(
        self, tool_input: AnnotateSomInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        try:
            image = tool_input.image or (
                context.resources.get(tool_input.image_ref, context.task_id, "image")
                if context is not None and tool_input.image_ref is not None
                else None
            )
        except ResourceError as error:
            return ToolReceipt.failure(
                self.name, ToolFailureCode.INVALID_INPUT, str(error)
            )
        if image is None:
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.INVALID_INPUT,
                "image_ref requires task context",
            )
        annotated = image.convert("RGB").copy()
        draw = ImageDraw.Draw(annotated)
        annotations: list[dict[str, object]] = []
        for mark in tool_input.marks:
            right, bottom = mark.left + mark.width, mark.top + mark.height
            draw.rectangle((mark.left, mark.top, right, bottom), outline="red", width=2)
            draw.text((mark.left, mark.top), mark.label, fill="red")
            annotations.append(
                {
                    "label": mark.label,
                    "bounds": {
                        "left": mark.left,
                        "top": mark.top,
                        "width": mark.width,
                        "height": mark.height,
                    },
                }
            )
        data: dict[str, object] = {"annotations": annotations}
        if context is None:
            data["image"] = annotated
        else:
            data["image_ref"] = context.resources.put(
                context.task_id, "image", annotated
            ).model_dump()
        return ToolReceipt(tool_name=self.name, success=True, data=data)
