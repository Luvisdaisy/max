"""Online-Mind2Web v2 轨迹的原子记录、映射和本地验证。

轨迹只写入本项目的评测结果目录；它在工具动作发生时复制对应截图，绝不从普通运行 JSONL 反推敏感参数。
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from max_gui.mind2web.models import OnlineMind2WebTask, SafetyRule

_SENSITIVE_INPUT = re.compile(r"(?:password|passwd|cvv|cvc|card\s*number|密码|银行卡)", re.I)


class TrajectoryValidationError(ValueError):
    """导出的 v2 轨迹不满足 WebJudge 前置条件时抛出。"""


@dataclass(slots=True)
class EvaluationStepRecorder:
    """把 AgentRunner 的可选回调转化为 v2 action history。"""

    task: OnlineMind2WebTask
    rule: SafetyRule
    result_dir: Path
    current_url: Callable[[], str | None]
    steps: list[dict[str, Any]] = field(default_factory=list)
    last_move: tuple[int, int] | None = None
    final_answer: str | None = None
    blocked_reason: str | None = None
    completion_declared: bool = False
    completion_post_observation: bool = False

    def __post_init__(self) -> None:
        """创建本题轨迹截图目录。"""
        (self.result_dir / "trajectory").mkdir(parents=True, exist_ok=True)

    def record(self, payload: dict[str, Any]) -> None:
        """接收一个已执行动作并在有网页语义时写入轨迹步骤。

        参数：`payload` 是 AgentRunner 在评测模式传来的已解析工具调用。观察类工具不会生成 v2 action。
        副作用：复制截图并追加自包含步骤；不允许的输入会停止后续导出。
        """
        name = str(payload.get("tool_name") or "")
        arguments = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        if payload.get("completion_post_observation"):
            self.completion_post_observation = bool(payload.get("ok")) and bool(
                payload.get("images")
            )
            return
        if payload.get("ok") is False:
            return
        if name == "mouse_move":
            x, y = _coordinates(arguments)
            if x is not None and y is not None:
                self.last_move = (x, y)
        action = _map_action(name, arguments, self.last_move)
        if action is None:
            return
        if len(self.steps) >= self.rule.max_steps:
            self.blocked_reason = "达到安全清单最大动作数"
            return
        if action["action_type"] == "TYPE" and _SENSITIVE_INPUT.search(
            action["action_description"]
        ):
            self.blocked_reason = "轨迹输入命中敏感模式"
            return
        image = _copy_latest_image(
            payload.get("images"), self.result_dir / "trajectory", len(self.steps)
        )
        if image is None:
            self.blocked_reason = "网页动作缺少对应截图"
            return
        url = self.current_url()
        if not url:
            self.blocked_reason = "无法读取专用浏览器当前 URL"
            return
        step = {
            "step": len(self.steps),
            "screenshot": image.name,
            "url": url,
            "action": action,
            "thought": payload.get("reasoning"),
        }
        self.steps.append(step)
        if action["action_type"] == "TASK_COMPLETE":
            self.completion_declared = True
            self.final_answer = str(
                arguments.get("summary") or arguments.get("evidence") or "任务已完成"
            )

    def result(self) -> dict[str, Any]:
        """返回可写入 `result.json` 的 v2 自包含对象。"""
        return {
            "schema_version": "online-mind2web-v2",
            "task_id": self.task.task_id,
            "task": self.task.instruction,
            "website": self.task.website,
            "reference_length": self.task.reference_length,
            "action_history": self.steps,
            "agent_final_answer": self.final_answer,
        }

    def write_and_validate(self) -> Path:
        """校验并写入本题 `result.json`。

        异常：发生安全阻断或 v2 字段不完整时抛出 `TrajectoryValidationError`。
        """
        if self.blocked_reason:
            raise TrajectoryValidationError(self.blocked_reason)
        if not self.completion_declared:
            raise TrajectoryValidationError("任务未成功声明 task_complete")
        if not self.completion_post_observation:
            raise TrajectoryValidationError("任务完成后缺少独立后置截图")
        payload = self.result()
        validate_v2(payload, self.result_dir)
        target = self.result_dir / "result.json"
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target


def validate_v2(payload: dict[str, Any], result_dir: Path) -> None:
    """验证 Online-Mind2Web v2 的最小可判分契约。

    参数：`payload` 为待提交对象，`result_dir` 为截图相对路径根。
    异常：字段、步骤顺序、截图、URL、终止动作或答案不符合约定时抛出。
    """
    required = {
        "schema_version",
        "task_id",
        "task",
        "reference_length",
        "action_history",
        "agent_final_answer",
    }
    missing = required - payload.keys()
    if missing or payload.get("schema_version") != "online-mind2web-v2":
        raise TrajectoryValidationError(f"v2 轨迹缺字段或版本错误：{sorted(missing)}")
    if not isinstance(payload["reference_length"], int) or payload["reference_length"] <= 0:
        raise TrajectoryValidationError("reference_length 必须为正整数")
    steps = payload["action_history"]
    if not isinstance(steps, list) or not steps:
        raise TrajectoryValidationError("action_history 不能为空")
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or step.get("step") != index:
            raise TrajectoryValidationError("步骤编号必须从 0 连续递增")
        screenshot = step.get("screenshot")
        if (
            not isinstance(screenshot, str)
            or not (result_dir / "trajectory" / screenshot).is_file()
        ):
            raise TrajectoryValidationError("每步必须引用存在的截图")
        if not isinstance(step.get("url"), str) or not step["url"].startswith(
            ("http://", "https://")
        ):
            raise TrajectoryValidationError("每步必须有 HTTP(S) URL")
        if "thought" not in step or not isinstance(step.get("action"), dict):
            raise TrajectoryValidationError("每步必须包含 thought 与 action")
    if steps[-1]["action"].get("action_type") != "TASK_COMPLETE":
        raise TrajectoryValidationError("最后一步必须是 TASK_COMPLETE")
    if (
        not isinstance(payload.get("agent_final_answer"), str)
        or not payload["agent_final_answer"].strip()
    ):
        raise TrajectoryValidationError("必须提供最终答案")


def _map_action(
    tool_name: str, arguments: dict[str, Any], last_move: tuple[int, int] | None
) -> dict[str, Any] | None:
    """将允许的桌面工具映射为上游 v2 动作，其余工具仅作为观察。"""
    if tool_name == "mouse_move":
        x, y = _coordinates(arguments)
        if x is None or y is None:
            return None
        return {"action_type": "HOVER", "action_description": f"HOVER({x},{y})"}
    if tool_name == "mouse_click":
        if last_move is None:
            return {"action_type": "CLICK", "action_description": "CLICK"}
        return {
            "action_type": "CLICK",
            "action_description": f"CLICK({last_move[0]},{last_move[1]})",
        }
    if tool_name == "mouse_scroll":
        return {
            "action_type": "SCROLL",
            "action_description": f"SCROLL({arguments.get('amount', 0)})",
        }
    if tool_name == "keyboard_type":
        return {"action_type": "TYPE", "action_description": str(arguments.get("text") or "")}
    if tool_name == "keyboard_press":
        return {
            "action_type": "PRESS_KEY",
            "action_description": "+".join(arguments.get("keys", [])),
        }
    if tool_name == "task_complete":
        return {"action_type": "TASK_COMPLETE", "action_description": "TASK_COMPLETE"}
    return None


def _coordinates(arguments: dict[str, Any]) -> tuple[int | None, int | None]:
    """读取当前 ViewFrame 下已解析的整数坐标。"""
    x, y = arguments.get("x"), arguments.get("y")
    return (x, y) if isinstance(x, int) and isinstance(y, int) else (None, None)


def _copy_latest_image(images: object, directory: Path, index: int) -> Path | None:
    """复制工具动作后截图，并返回相对轨迹文件路径。"""
    if not isinstance(images, list) or not images:
        return None
    source = Path(str(images[-1]))
    if not source.is_file():
        return None
    target = directory / f"{index:04d}{source.suffix or '.png'}"
    shutil.copy2(source, target)
    return target
