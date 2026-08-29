"""max-gui 包入口：再导出命令行主函数。

对外符号：
- `main`：解析参数并分发 TUI、评测与清理命令。
"""

from max_gui.cli import main

__all__ = ["main"]
