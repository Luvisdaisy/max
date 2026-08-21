"""max-gui 包入口：再导出命令行主函数。

对外符号：
- `main`：解析参数并分发 `tui` / `serve`。
"""

from max_gui.cli import main

__all__ = ["main"]
