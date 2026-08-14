"""工作区图像校验工具：缩放后报告 data URL 长度，供模型确认附件可用。"""

from __future__ import annotations

from pathlib import Path

from max_gui.config import Settings
from max_gui.inference.images import ImagePrepError, prepare_image
from max_gui.tools.paths import resolve_workspace_path
from max_gui.tools.protocol import Tool, ToolError


def image_tool(workspace: Path, settings: Settings) -> Tool:
    """构造 `prepare_image` 工具。

    参数：
        workspace: 图像必须位于此根下。
        settings: 提供 `max_image_edge` / `max_image_bytes`。
    """

    async def prepare(args: dict) -> str:
        """校验并缩放工作区图像。参数：`path`。"""
        path = resolve_workspace_path(workspace, str(args.get("path") or ""))
        try:
            prepared = prepare_image(
                path, max_edge=settings.max_image_edge, max_bytes=settings.max_image_bytes
            )
        except ImagePrepError as exc:
            raise ToolError(str(exc)) from exc
        url = prepared.part["image_url"]["url"]
        return f"已预处理图像 {path.name}，data URL 长度 {len(url)}"

    return Tool(
        name="prepare_image",
        description="校验并缩放工作区内图像，供后续模型调用",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        invoke=prepare,
    )
