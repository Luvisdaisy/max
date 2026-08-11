"""把本地 Agent 模型会话接入统一工具注册表。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from max_agent.orchestration.model_session import AgentModelError, AgentModelSession
from max_agent.orchestration.models import AgentMessage
from max_agent.tools.base import (
    ToolContext,
    ToolFailureCode,
    ToolPermission,
    ToolPhase,
    ToolReceipt,
)


class InvokeModelInput(BaseModel):
    messages: list[AgentMessage]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_mode: str = "fast"
    image_refs: list[dict[str, Any]] = Field(default_factory=list)


class InvokeModelTool:
    """运行时内部模型能力；模型本身不可递归选择该工具。"""

    name = "invoke_model"
    description = "Return final text or one structured tool use."
    permission = ToolPermission.MODEL
    allowed_phases = frozenset({ToolPhase.REASON})
    timeout_seconds = 120.0
    recoverable = False
    model_visible = False
    side_effect = False
    input_model = InvokeModelInput

    def __init__(self, session: AgentModelSession) -> None:
        self._session = session

    def invoke(
        self, tool_input: InvokeModelInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        images = []
        if context is not None:
            for raw_ref in tool_input.image_refs:
                from max_agent.orchestration.resources import ResourceRef

                images.append(
                    context.resources.get(
                        ResourceRef.model_validate(raw_ref), context.task_id, "image"
                    )
                )
        try:
            response = self._session.respond(
                tool_input.messages,
                tool_input.tools,
                reasoning_mode=tool_input.reasoning_mode,
                images=images,
                consume_correction=(lambda: context.consume_budget("corrections"))
                if context is not None
                else None,
            )
        except AgentModelError as error:
            return ToolReceipt.failure(
                self.name, ToolFailureCode.UNAVAILABLE, f"{error.code}: {error}"
            )
        return ToolReceipt(
            tool_name=self.name, success=True, data={"response": response.model_dump()}
        )
