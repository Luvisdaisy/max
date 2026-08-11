"""任务内图像预处理与模板匹配工具。"""

from __future__ import annotations

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from max_agent.orchestration.resources import ResourceError, ResourceRef
from max_agent.tools.base import (
    ToolContext,
    ToolFailureCode,
    ToolPermission,
    ToolPhase,
    ToolReceipt,
)


class _ImageInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image_ref: ResourceRef | None = None
    image: Image.Image | None = None

    @model_validator(mode="after")
    def require_source(self) -> "_ImageInput":
        if (self.image_ref is None) == (self.image is None):
            raise ValueError("provide exactly one image_ref or image")
        return self


class PreprocessImageInput(_ImageInput):
    grayscale: bool = True
    threshold: int | None = Field(default=None, ge=0, le=255)


class MatchTemplateInput(_ImageInput):
    template_ref: ResourceRef | None = None
    template: Image.Image | None = None
    minimum_score: float = Field(default=0.8, ge=-1.0, le=1.0)

    @model_validator(mode="after")
    def require_template(self) -> "MatchTemplateInput":
        if (self.template_ref is None) == (self.template is None):
            raise ValueError("provide exactly one template_ref or template")
        return self


class _VisionTool:
    permission = ToolPermission.OBSERVE
    allowed_phases = frozenset({ToolPhase.TOOL, ToolPhase.OBSERVE_AFTER_ACTION})
    timeout_seconds = 15.0
    recoverable = True
    model_visible = True
    side_effect = False
    read_only = True


class PreprocessImageTool(_VisionTool):
    name = "preprocess_image"
    description = "Preprocess a task image without persisting it."
    input_model = PreprocessImageInput

    def invoke(
        self, tool_input: PreprocessImageInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        import cv2
        import numpy

        try:
            source = _resolve(tool_input.image, tool_input.image_ref, context)
        except ResourceError as error:
            return ToolReceipt.failure(
                self.name, ToolFailureCode.INVALID_INPUT, str(error)
            )
        image = numpy.array(source.convert("RGB"))
        if tool_input.grayscale:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if tool_input.threshold is not None:
            _, image = cv2.threshold(
                image, tool_input.threshold, 255, cv2.THRESH_BINARY
            )
        result = Image.fromarray(image)
        data: dict[str, object] = {"width": source.width, "height": source.height}
        if context is None:
            data["image"] = result
        else:
            data["image_ref"] = context.resources.put(
                context.task_id, "image", result
            ).model_dump()
        return ToolReceipt(tool_name=self.name, success=True, data=data)


class MatchTemplateTool(_VisionTool):
    name = "match_template"
    description = "Match a task-scoped template against a task image."
    input_model = MatchTemplateInput

    def invoke(
        self, tool_input: MatchTemplateInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        import cv2
        import numpy

        try:
            image = _resolve(tool_input.image, tool_input.image_ref, context)
            template = _resolve(tool_input.template, tool_input.template_ref, context)
        except ResourceError as error:
            return ToolReceipt.failure(
                self.name, ToolFailureCode.INVALID_INPUT, str(error)
            )
        source_array = numpy.array(image.convert("L"))
        template_array = numpy.array(template.convert("L"))
        if (
            template_array.shape[0] > source_array.shape[0]
            or template_array.shape[1] > source_array.shape[1]
        ):
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.INVALID_INPUT,
                "template is larger than image",
            )
        scores = cv2.matchTemplate(source_array, template_array, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(scores)
        matches = []
        if score >= tool_input.minimum_score:
            matches.append(
                {
                    "score": float(score),
                    "bounds": {
                        "left": int(location[0]),
                        "top": int(location[1]),
                        "width": template.width,
                        "height": template.height,
                    },
                }
            )
        return ToolReceipt(tool_name=self.name, success=True, data={"matches": matches})


def _resolve(
    image: Image.Image | None, ref: ResourceRef | None, context: ToolContext | None
) -> Image.Image:
    if image is not None:
        return image
    if context is None or ref is None:
        raise ResourceError("image_ref requires task context")
    return context.resources.get(ref, context.task_id, "image")
