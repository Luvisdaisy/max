"""Set-of-Mark 标注工具：为调用方提供的图像标记候选区域。"""

from __future__ import annotations

from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict, Field

from max_agent.tools.base import ToolReceipt


class SomMark(BaseModel):
    label: str = Field(min_length=1)
    left: int = Field(ge=0)
    top: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class AnnotateSomInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    image: Image.Image
    marks: list[SomMark]


class AnnotateSomTool:
    """生成标注结果，但不执行点击、输入或其他桌面控制操作。"""

    name = "annotate_som"
    input_model = AnnotateSomInput

    def invoke(self, tool_input: AnnotateSomInput) -> ToolReceipt:
        annotated = tool_input.image.convert("RGB").copy()
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
        return ToolReceipt(
            tool_name=self.name,
            success=True,
            data={"image": annotated, "annotations": annotations},
        )
