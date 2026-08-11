"""动作结果验证、有限恢复与脱敏运行归档工具。"""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from max_agent.artifacts import ExperimentArchive
from max_agent.orchestration.models import (
    DesktopAction,
    StandardObservation,
    summarize_data,
)
from max_agent.tools.base import ToolContext, ToolPermission, ToolPhase, ToolReceipt


class VerifyResultInput(BaseModel):
    user_goal: str
    action: DesktopAction
    before: StandardObservation
    after: StandardObservation


class VerifyResultTool:
    name = "verify_result"
    description = "Verify an action from a fresh observation."
    permission = ToolPermission.VERIFY
    allowed_phases = frozenset({ToolPhase.VERIFY})
    timeout_seconds = 10.0
    recoverable = True
    model_visible = False
    side_effect = False
    input_model = VerifyResultInput

    def invoke(
        self, tool_input: VerifyResultInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        action = tool_input.action
        before, after = tool_input.before, tool_input.after
        completed = False
        evidence: list[str] = []
        target_is_foreground = _same_window(action.window, after.foreground_window)
        if action.kind == "activate_window" and action.window is not None:
            completed = target_is_foreground
            if completed:
                evidence.append("foreground_window_matches_target")
        elif action.kind == "type_text" and action.text:
            recognized = "\n".join(
                str(line.get("text", "")) for line in after.ocr_lines
            )
            # 输入回执只能证明适配器发出了事件；成功必须由目标窗口上的新 OCR 证据确认。
            completed = target_is_foreground and _contains_normalized(
                recognized, action.text
            )
            if completed:
                evidence.append("foreground_window_matches_target")
                evidence.append(
                    f"ocr_contains_input_sha256:{hashlib.sha256(action.text.encode()).hexdigest()}"
                )
        else:
            completed = before.fingerprint != after.fingerprint or bool(
                after.changed_regions
            )
            if completed:
                evidence.append("desktop_state_changed")
        changed_area = sum(
            region.width * region.height for region in after.changed_regions
        )
        total_area = after.bounds.width * after.bounds.height
        return ToolReceipt(
            tool_name=self.name,
            success=True,
            data={
                "completed": completed,
                "no_progress": before.fingerprint == after.fingerprint,
                "changed_ratio": changed_area / total_area if total_area else 0.0,
                "evidence": evidence,
                "after_fingerprint": after.fingerprint,
            },
        )


class RecoverInput(BaseModel):
    no_progress_count: int = Field(ge=0)
    remaining_recoveries: int = Field(ge=0)


class RecoverTool:
    name = "recover"
    description = "Return one bounded recovery transition without executing input."
    permission = ToolPermission.RECOVER
    allowed_phases = frozenset({ToolPhase.RECOVER})
    timeout_seconds = 5.0
    recoverable = False
    model_visible = False
    side_effect = False
    input_model = RecoverInput

    def invoke(
        self, tool_input: RecoverInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        if tool_input.remaining_recoveries <= 0:
            decision: Literal["fail", "reobserve", "deliberate_reason", "wait_user"] = (
                "fail"
            )
        elif tool_input.no_progress_count <= 1:
            decision = "reobserve"
        elif tool_input.no_progress_count == 2:
            decision = "deliberate_reason"
        else:
            decision = "wait_user"
        return ToolReceipt(
            tool_name=self.name, success=True, data={"decision": decision}
        )


class ArchiveRunInput(BaseModel):
    task_id: str
    status: str
    config: dict[str, Any] = Field(default_factory=dict)
    trajectory: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class ArchiveRunTool:
    name = "archive_run"
    description = "Persist only a sanitized runtime audit projection."
    permission = ToolPermission.ARCHIVE
    allowed_phases = frozenset({ToolPhase.ARCHIVE})
    timeout_seconds = 10.0
    recoverable = False
    model_visible = False
    side_effect = False
    input_model = ArchiveRunInput

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root

    def invoke(
        self, tool_input: ArchiveRunInput, context: ToolContext | None = None
    ) -> ToolReceipt:
        archive = ExperimentArchive.create(self._artifact_root, "agent")
        archive.write_config(summarize_data(tool_input.config))
        archive.write_environment({"task_id": tool_input.task_id, "offline": True})
        for item in tool_input.trajectory:
            archive.append_trajectory(summarize_data(item))
        archive.write_result(summarize_data(tool_input.result))
        return ToolReceipt(
            tool_name=self.name,
            success=True,
            data={"archived": True, "status": tool_input.status},
        )


def _same_window(expected: Any, actual: Any) -> bool:
    """窗口标题可能变化，授权身份仅由 HWND、PID 与规范化程序路径决定。"""
    if expected is None or actual is None:
        return expected is actual
    return (
        expected.hwnd == actual.hwnd
        and expected.process_id == actual.process_id
        and expected.executable_path.casefold() == actual.executable_path.casefold()
    )


def _contains_normalized(recognized: str, expected: str) -> bool:
    """OCR 行拆分、空白与大小写不影响包含判断，字符内容仍必须一致。"""

    def normalize(value: str) -> str:
        return "".join(unicodedata.normalize("NFKC", value).casefold().split())

    normalized_expected = normalize(expected)
    return bool(normalized_expected) and normalized_expected in normalize(recognized)
