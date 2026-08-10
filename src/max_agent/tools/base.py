"""定义所有工具共享的输入失败表示、回执结构和调用协议。"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ToolFailureCode(StrEnum):
    """工具调用失败的稳定分类，便于编排器决定恢复策略。"""

    INVALID_INPUT = "invalid_input"
    UNKNOWN_TOOL = "unknown_tool"
    UNAVAILABLE = "unavailable"
    EXECUTION_FAILED = "execution_failed"


class ToolError(BaseModel):
    code: ToolFailureCode
    message: str


class ToolReceipt(BaseModel):
    """工具的结构化成功或失败回执，不直接泄露底层异常对象。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    tool_name: str
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: ToolError | None = None

    @classmethod
    def failure(
        cls, tool_name: str, code: ToolFailureCode, message: str
    ) -> ToolReceipt:
        return cls(
            tool_name=tool_name,
            success=False,
            error=ToolError(code=code, message=message),
        )


class Tool(Protocol):
    """注册表可调用工具的最小契约。"""

    name: str
    input_model: type[BaseModel]

    def invoke(self, tool_input: BaseModel) -> ToolReceipt: ...
