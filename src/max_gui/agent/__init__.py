"""ReAct Agent 包：图运行器、状态类型、GUI 契约与迭代上限文案。

对外符号：
- `AgentRunner`：驱动 Think / Act / Observe。
- `AgentState`：LangGraph 状态字典。
- `ITERATION_LIMIT_MESSAGE`：达到 `max_iterations` 时写入会话的说明。
- `GUI_SYSTEM_PROMPT`：固定中文 GUI 契约正文。
- `compose_gui_system_prompt`：加上 OS 与当前视图宽高后的完整 system。
"""

from max_gui.agent.graph import ITERATION_LIMIT_MESSAGE, AgentRunner
from max_gui.agent.prompts import GUI_SYSTEM_PROMPT, compose_gui_system_prompt
from max_gui.agent.state import AgentState

__all__ = [
    "GUI_SYSTEM_PROMPT",
    "ITERATION_LIMIT_MESSAGE",
    "AgentRunner",
    "AgentState",
    "compose_gui_system_prompt",
]
