from __future__ import annotations

from max_gui.config import Settings
from max_gui.tools.registry import DenyGate, build_default_registry


async def test_read_file_and_reject_escape(settings: Settings) -> None:
    notes = settings.workspace / "notes.md"
    notes.write_text("hello workspace", encoding="utf-8")
    registry = build_default_registry(settings)
    assert "hello workspace" == await registry.invoke("read_file", {"path": "notes.md"})
    denied = await registry.invoke("read_file", {"path": "../outside.txt"})
    assert "权限" in denied


async def test_search_files(settings: Settings) -> None:
    (settings.workspace / "a.txt").write_text("alpha token here", encoding="utf-8")
    registry = build_default_registry(settings)
    result = await registry.invoke("search_files", {"query": "token"})
    assert "a.txt" in result
    assert "token" in result


async def test_run_python_success_and_timeout(settings: Settings) -> None:
    registry = build_default_registry(settings)
    ok = await registry.invoke("run_python", {"code": "print(1+1)"})
    assert "2" in ok
    assert "exit: 0" in ok
    timed = await registry.invoke("run_python", {"code": "import time; time.sleep(5)"})
    assert "超时" in timed


async def test_unknown_tool_and_confirmation_deny(settings: Settings) -> None:
    registry = build_default_registry(settings, gate=DenyGate())
    unknown = await registry.invoke("not_a_tool", {})
    assert "未知工具" in unknown
    cancelled = await registry.invoke("write_file", {"path": "x.txt", "content": "nope"})
    assert "已取消" in cancelled
    assert not (settings.workspace / "x.txt").exists()
    cancelled_py = await registry.invoke("run_python", {"code": "print(1)"})
    assert "已取消" in cancelled_py
