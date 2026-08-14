from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

from max_gui.tools.protocol import Tool, ToolError

_BLOCKED_IMPORTS = {"pyautogui", "pyscreeze", "pynput"}


def _blocked_desktop_import(code: str) -> str | None:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name.split(".", 1)[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module.split(".", 1)[0]]
        else:
            continue
        for name in names:
            if name in _BLOCKED_IMPORTS:
                return name
    return None


def python_tool(workspace: Path, timeout: float) -> Tool:
    async def run_python(args: dict) -> str:
        code = str(args.get("code") or "")
        blocked = _blocked_desktop_import(code)
        if blocked:
            raise ToolError(f"禁止经 run_python 导入 {blocked} 绕过桌面工具")
        try:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            return f"超时（{timeout}s）\nstdout:\n{stdout}\nstderr:\n{stderr}\nexit: timeout"
        return (
            f"stdout:\n{completed.stdout}"
            f"\nstderr:\n{completed.stderr}"
            f"\nexit: {completed.returncode}"
        )

    return Tool(
        name="run_python",
        description="在工作区目录下以子进程执行 Python 片段",
        parameters={
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
        invoke=run_python,
        confirmation_scope="workspace",
    )
