from __future__ import annotations

from pathlib import Path

from max_gui.config import Settings
from max_gui.inference.images import ImagePrepError, prepare_image
from max_gui.tools.paths import resolve_workspace_path
from max_gui.tools.protocol import Tool, ToolError


def image_tool(workspace: Path, settings: Settings) -> Tool:
    async def prepare(args: dict) -> str:
        path = resolve_workspace_path(workspace, str(args.get("path") or ""))
        try:
            part = prepare_image(
                path, max_edge=settings.max_image_edge, max_bytes=settings.max_image_bytes
            )
        except ImagePrepError as exc:
            raise ToolError(str(exc)) from exc
        url = part["image_url"]["url"]
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
