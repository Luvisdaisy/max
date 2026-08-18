"""ReAct Agent 包：图运行器、状态类型、GUI 契约与迭代上限文案。

对外符号：
- `AgentRunner`：驱动 Think / Act / Observe。
- `AgentState`：LangGraph 状态字典。
- `ITERATION_LIMIT_MESSAGE`：达到 `max_iterations` 时写入会话的说明。
- `GUI_SYSTEM_PROMPT`：每次 think 注入的中文 GUI 契约。
"""

from max_gui.agent.graph import ITERATION_LIMIT_MESSAGE, AgentRunner
from max_gui.agent.prompts import GUI_SYSTEM_PROMPT
from max_gui.agent.state import AgentState

__all__ = ["GUI_SYSTEM_PROMPT", "ITERATION_LIMIT_MESSAGE", "AgentRunner", "AgentState"]
