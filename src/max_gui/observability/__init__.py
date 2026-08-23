"""本地运行可观测性：结构化事件、JSONL 记录与开发诊断。

对外符号：
- `RunEvent` / `RunEventType`：一次运行中的版本化事件。
- `RunRecorder`：为单次运行分配顺序号、追加事件并汇总统计（含已知 token 用量）。
- `usage_from_data`：从事件载荷取出完整用量，未知则返回 `None`。
- `new_run_id`：生成不依赖会话编号的运行编号。
- `safe_error_summary`：收敛异常正文并遮蔽常见密钥格式。
"""

from max_gui.observability.events import (
    RunEvent,
    RunEventType,
    new_run_id,
    safe_error_summary,
)
from max_gui.observability.recorder import RunRecorder, usage_from_data

__all__ = [
    "RunEvent",
    "RunEventType",
    "RunRecorder",
    "new_run_id",
    "safe_error_summary",
    "usage_from_data",
]
