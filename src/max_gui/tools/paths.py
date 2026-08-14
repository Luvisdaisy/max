from __future__ import annotations

from pathlib import Path

from max_gui.tools.protocol import ToolError


def resolve_workspace_path(workspace: Path, raw: str) -> Path:
    root = workspace.resolve()
    candidate = Path(raw)
    path = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ToolError(f"权限错误：路径逃出工作区：{raw}") from exc
    return path
