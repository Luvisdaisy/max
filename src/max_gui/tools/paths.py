"""工作区路径解析：把相对路径钉在工作区根内，拒绝逃逸。"""

from __future__ import annotations

from pathlib import Path

from max_gui.tools.protocol import ToolError


def resolve_workspace_path(workspace: Path, raw: str) -> Path:
    """把用户给出的路径解析为工作区内的绝对路径。

    相对路径相对 `workspace`；绝对路径也必须落在工作区根之下。

    参数：
        workspace: 工作区根目录。
        raw: 工具参数里的路径字符串。

    返回：
        解析后的绝对路径。

    异常：
        ToolError: 解析结果逃出工作区。
    """
    root = workspace.resolve()
    candidate = Path(raw)
    path = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ToolError(f"权限错误：路径逃出工作区：{raw}") from exc
    return path


def _is_under(path: Path, root: Path) -> bool:
    """`path` 是否位于 `root` 之内（含根目录本身）。"""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def resolve_ocr_path(workspace: Path, screenshots_dir: Path, raw: str) -> Path:
    """把 OCR 路径限制在工作区或截图目录内。

    相对路径先看工作区已有文件，否则再看截图目录。不检查文件是否存在，
    以便调用方在缺文件时跳过启动推理。

    参数：
        workspace: 工作区根。
        screenshots_dir: 截图目录。
        raw: 工具参数里的路径。

    返回：
        解析后的绝对路径。

    异常：
        ToolError: 空路径，或结果不在两个根之内。
    """
    text = str(raw or "").strip()
    if not text:
        raise ToolError("ocr 需要 path")
    candidate = Path(text)
    workspace_root = workspace.resolve()
    shots_root = screenshots_dir.resolve()
    if candidate.is_absolute():
        path = candidate.resolve()
    else:
        workspace_path = (workspace_root / candidate).resolve()
        shots_path = (shots_root / candidate).resolve()
        if _is_under(workspace_path, workspace_root) and workspace_path.is_file():
            path = workspace_path
        elif _is_under(shots_path, shots_root):
            path = shots_path
        else:
            path = workspace_path
    if not (_is_under(path, workspace_root) or _is_under(path, shots_root)):
        raise ToolError(f"权限错误：路径逃出截图目录与工作区：{raw}")
    return path
