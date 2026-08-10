"""Agent 能力工具的契约与注册入口。"""

from max_agent.tools.registry import ToolRegistry, build_default_registry

__all__ = ["ToolRegistry", "build_default_registry"]
"""通过注册表向编排器提供的工具契约与实现。"""
