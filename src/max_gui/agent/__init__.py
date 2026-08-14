"""ReAct Agent 包：图运行器、状态类型与迭代上限文案。

对外符号：
- `AgentRunner`：驱动 Think / Act / Observe。
- `AgentState`：LangGraph 状态字典。
- `ITERATION_LIMIT_MESSAGE`：达到 `max_iterations` 时写入会话的说明。
"""

from max_gui.agent.graph import ITERATION_LIMIT_MESSAGE, AgentRunner
from max_gui.agent.state import AgentState

__all__ = ["ITERATION_LIMIT_MESSAGE", "AgentRunner", "AgentState"]
