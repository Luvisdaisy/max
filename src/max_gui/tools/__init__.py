"""Agent 工具：协议、注册表与默认工具集。

对外符号：
- `Tool` / `ToolResult` / `ToolError`：工具定义、多模态结果与业务错误。
- `ToolRegistry`：按名调用并走确认门。
- `build_default_registry`：装配文件、搜索、图像、OCR / 文字定位与桌面工具。
"""

from max_gui.tools.protocol import Tool, ToolError, ToolResult
from max_gui.tools.registry import ToolRegistry, build_default_registry

__all__ = ["Tool", "ToolError", "ToolRegistry", "ToolResult", "build_default_registry"]
