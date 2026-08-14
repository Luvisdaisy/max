from __future__ import annotations

from pathlib import Path

from max_gui.tools.paths import resolve_workspace_path
from max_gui.tools.protocol import Tool

_SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "model", ".pytest_cache"}
_SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".safetensors", ".bin", ".pyc"}


def search_tool(workspace: Path) -> Tool:
    async def search_files(args: dict) -> str:
        query = str(args.get("query") or "")
        if not query:
            return "查询为空"
        root = resolve_workspace_path(workspace, str(args.get("path") or "."))
        hits: list[str] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in _SKIP_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for index, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    rel = path.relative_to(workspace.resolve())
                    hits.append(f"{rel}:{index}: {line.strip()}")
                    if len(hits) >= 50:
                        return "\n".join(hits)
        return "\n".join(hits) if hits else "无匹配"

    return Tool(
        name="search_files",
        description="在工作区内搜索文件内容，返回路径与摘录",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["query"],
        },
        invoke=search_files,
    )
