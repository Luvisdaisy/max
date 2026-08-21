"""工作区文件工具：读、写、列目录，路径不得逃出工作区。"""

from __future__ import annotations

from pathlib import Path

from max_gui.tools.paths import resolve_workspace_path
from max_gui.tools.protocol import Tool, ToolError


def file_tools(workspace: Path) -> list[Tool]:
    """构造 `read_file` / `write_file` / `list_dir`。

    参数：
        workspace: 读写根目录。

    返回：
        三个工具；写文件不再走确认门。
    """

    async def read_file(args: dict) -> str:
        """读取工作区内文本文件。参数：`path`。"""
        path = resolve_workspace_path(workspace, str(args.get("path") or ""))
        if not path.is_file():
            raise ToolError(f"文件不存在：{path}")
        return path.read_text(encoding="utf-8", errors="replace")

    async def write_file(args: dict) -> str:
        """写入工作区内文本文件。参数：`path`、`content`。"""
        path = resolve_workspace_path(workspace, str(args.get("path") or ""))
        path.parent.mkdir(parents=True, exist_ok=True)
        content = str(args.get("content") or "")
        path.write_text(content, encoding="utf-8")
        return f"已写入 {path}（{len(content)} 字符）"

    async def list_dir(args: dict) -> str:
        """列出工作区目录。参数：`path`，默认 `.`。"""
        raw = str(args.get("path") or ".")
        path = resolve_workspace_path(workspace, raw)
        if not path.is_dir():
            raise ToolError(f"目录不存在：{path}")
        names = sorted(item.name + ("/" if item.is_dir() else "") for item in path.iterdir())
        return "\n".join(names) if names else "(空目录)"

    return [
        Tool(
            name="read_file",
            description="读取工作区内文本文件",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "相对工作区的路径"}},
                "required": ["path"],
            },
            invoke=read_file,
        ),
        Tool(
            name="write_file",
            description="写入工作区内文本文件",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            invoke=write_file,
        ),
        Tool(
            name="list_dir",
            description="列出工作区内目录",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            invoke=list_dir,
        ),
    ]
