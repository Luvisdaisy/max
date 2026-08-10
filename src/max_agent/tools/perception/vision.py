"""纯本地图像预处理与模板匹配工具，不访问屏幕或外部服务。"""

from __future__ import annotations

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from max_agent.tools.base import ToolFailureCode, ToolReceipt


class _ImageInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image: Image.Image


class PreprocessImageInput(_ImageInput):
    grayscale: bool = True
    threshold: int | None = Field(default=None, ge=0, le=255)


class MatchTemplateInput(_ImageInput):
    template: Image.Image
    minimum_score: float = Field(default=0.8, ge=-1.0, le=1.0)


class PreprocessImageTool:
    """对调用方提供的图像执行受限预处理并返回结果元数据。"""

    name = "preprocess_image"
    input_model = PreprocessImageInput

    def invoke(self, tool_input: PreprocessImageInput) -> ToolReceipt:
        import cv2
        import numpy

        image = numpy.array(tool_input.image.convert("RGB"))
        if tool_input.grayscale:
            image = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        if tool_input.threshold is not None:
            _, image = cv2.threshold(
                image, tool_input.threshold, 255, cv2.THRESH_BINARY
            )
        return ToolReceipt(
            tool_name=self.name,
            success=True,
            data={
                "image": Image.fromarray(image),
                "width": tool_input.image.width,
                "height": tool_input.image.height,
            },
        )


class MatchTemplateTool:
    """在调用方提供的源图与模板间计算匹配结果。"""

    name = "match_template"
    input_model = MatchTemplateInput

    def invoke(self, tool_input: MatchTemplateInput) -> ToolReceipt:
        import cv2
        import numpy

        source = numpy.array(tool_input.image.convert("L"))
        template = numpy.array(tool_input.template.convert("L"))
        if template.shape[0] > source.shape[0] or template.shape[1] > source.shape[1]:
            return ToolReceipt.failure(
                self.name,
                ToolFailureCode.INVALID_INPUT,
                "template is larger than image",
            )
        scores = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(scores)
        matches = []
        if score >= tool_input.minimum_score:
            matches.append(
                {
                    "score": float(score),
                    "bounds": {
                        "left": int(location[0]),
                        "top": int(location[1]),
                        "width": tool_input.template.width,
                        "height": tool_input.template.height,
                    },
                }
            )
        return ToolReceipt(tool_name=self.name, success=True, data={"matches": matches})
