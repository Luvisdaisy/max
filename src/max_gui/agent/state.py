"""LangGraph ReAct 状态：会话消息、待执行工具调用、计划与回合状态。"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from max_gui.agent.context import TaskContext

AgentStatus = Literal["thinking", "acting", "observing", "done", "error", "interrupted"]


class AgentState(TypedDict, total=False):
    """单回合在图节点之间传递的可变状态。

    字段：
        session_id: 当前会话编号。
        run_id: 当前用户任务的运行编号；旧检查点可缺省。
        messages: OpenAI 风格消息列表，content 多为 `{text, images}`。
        images: 本回合用户附带的图像路径。
        pending_tool_calls: Think 产出的调用，或 Act 写回的工具结果。
        iteration: 已完成的 Think-Act-Observe 圈数。
        status: 当前节点或终态。
        error: 失败时的人类可读说明。
        plan: 编号子任务列表；旧检查点可缺省。
        current_subtask: 当前子任务文案；无计划时为空。
        task_context: 当前用户任务的最小推理上下文；不重放全量会话历史。
        history_message_count: 任务开始前会话的消息数，只供上下文裁剪诊断。
        allowed_tools: 产生当前模型回复时实际暴露的工具名，用于 act 二次门禁。
        context_diagnostics: 本轮上下文预算的脱敏计数。
    """

    session_id: str
    run_id: str
    messages: list[dict[str, Any]]
    images: list[str]
    pending_tool_calls: list[dict[str, Any]]
    iteration: int
    status: AgentStatus
    error: str | None
    plan: list[str]
    current_subtask: str | None
    task_context: TaskContext
    history_message_count: int
    allowed_tools: list[str]
    context_diagnostics: dict[str, Any]
