"""默认 AgentRuntime 的依赖装配，不包含任何前端实现。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from max_agent.orchestration.graph import AgentRuntime
from max_agent.orchestration.model_session import (
    AgentModelSession,
    LocalAgentModelSession,
)
from max_agent.orchestration.session import InputStateCleaner
from max_agent.tools.control import (
    DesktopActionProposalTool,
    DesktopAdapter,
    ExecuteActionTool,
    GuardActionTool,
    RequestUserTool,
)
from max_agent.tools.model import InvokeModelTool
from max_agent.tools.registry import ToolRegistry, build_default_registry
from max_agent.tools.verification import ArchiveRunTool, RecoverTool, VerifyResultTool


def build_agent_runtime(
    repository_root: Path,
    artifact_root: Path,
    selected_model: Callable[[], str],
    *,
    model_session: AgentModelSession | None = None,
    desktop_adapter: DesktopAdapter | None = None,
    registry: ToolRegistry | None = None,
) -> AgentRuntime:
    """组装完整工具集合；模型只看到显式标记的安全子集。"""
    session = model_session or LocalAgentModelSession(repository_root, selected_model)
    tools = registry or build_default_registry(
        ocr_model_dir=repository_root / "model" / "ocr"
    )
    execute = ExecuteActionTool(desktop_adapter)
    for tool in (
        InvokeModelTool(session),
        RequestUserTool(),
        DesktopActionProposalTool(),
        GuardActionTool(),
        execute,
        VerifyResultTool(),
        RecoverTool(),
        ArchiveRunTool(artifact_root),
    ):
        if tools.get(tool.name) is None:
            tools.register(tool)
    cleaner = InputStateCleaner((execute.adapter.release_all,))
    return AgentRuntime(tools, cleaner=cleaner, reset_model=session.reset)
