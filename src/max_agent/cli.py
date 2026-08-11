from __future__ import annotations

import argparse
from pathlib import Path

from .artifacts import ExperimentArchive
from .console_core import (
    ConsoleEvent,
    ConsoleEventKind,
    EventSink,
    OperationResult,
    SessionStatus,
    dispatch_input,
)
from .console_frontends import run_textual_chat
from .diagnostics import default_probe, render_doctor, run_diagnostics
from .local_llm import LocalChatRuntime, LocalRuntimeError
from .orchestration.graph import AgentRuntime
from .orchestration.models import AgentRequest, RuntimeEvent
from .runtime import build_agent_runtime


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _doctor_operation(
    artifact_root: Path, *, desktop_probe: bool = False
) -> OperationResult:
    archive = ExperimentArchive.create(artifact_root, "doctor")
    result = run_diagnostics(default_probe(desktop_probe=desktop_probe))
    archive.write_config({"command": "doctor", "desktop_probe": desktop_probe})
    archive.write_environment(result.to_dict())
    archive.append_trajectory({"event": "doctor_completed", "ok": result.ok})
    archive.write_result(
        {"status": "success" if result.ok else "failure", "failures": result.failures}
    )
    return OperationResult(
        "doctor",
        (ConsoleEvent(ConsoleEventKind.COMMAND, render_doctor(result)),),
        exit_code=0 if result.ok else 1,
    )


def _doctor(artifact_root: Path, *, desktop_probe: bool = False) -> int:
    operation = _doctor_operation(artifact_root, desktop_probe=desktop_probe)
    print(*(event.text for event in operation.events), sep="\n")
    return operation.exit_code


def _interactive_dispatch(
    artifact_root: Path,
    runtime: LocalChatRuntime,
    agent_runtime: AgentRuntime | None = None,
):
    """仅在 CLI 适配层把现有控制台协议连接到完整 AgentRuntime。"""
    agent = agent_runtime or build_agent_runtime(
        _repository_root(),
        artifact_root,
        lambda: runtime.selected_model,
    )

    def session_status() -> SessionStatus:
        """返回状态栏与 `/status` 命令共享的只读快照。"""
        agent_state = "waiting_user" if agent.suspended_task_id else runtime.state
        return SessionStatus(
            runtime.selected_model,
            agent_state,
            "本地 · Agent Guard · 受控桌面 · 无网络",
        )

    def chat(goal: str, emit: EventSink) -> str:
        """一个 UI 请求内运行有限多轮 text-or-tool 循环，并只映射净化事件。"""

        def report(event: RuntimeEvent) -> None:
            if event.phase == "reason":
                labels = {
                    "running": "Agent 正在判断下一步",
                    "succeeded": "Agent 已完成本轮判断",
                    "failed": "Agent 本轮判断失败",
                }
                emit(
                    ConsoleEvent(
                        ConsoleEventKind.NOTICE, labels[event.state], state=event.state
                    )
                )
                return
            emit(
                ConsoleEvent.tool(
                    event.tool_name or event.phase, event.state, event.elapsed_seconds
                )
            )

        return agent.run(AgentRequest(user_goal=goal), report).response_text

    def model_operation(model_name: str | None) -> OperationResult:
        if model_name is None:
            models = runtime.available_models()
            if not models:
                return OperationResult(
                    "model",
                    (
                        ConsoleEvent(
                            ConsoleEventKind.COMMAND, "未发现可选择的本地模型。"
                        ),
                    ),
                )
            lines = ["可选本地模型："]
            lines.extend(
                f"{'* ' if name == runtime.selected_model else '  '}{name}"
                for name in models
            )
            lines.append("使用 /model <模型目录> 切换模型。")
            return OperationResult(
                "model",
                (ConsoleEvent(ConsoleEventKind.COMMAND, "\n".join(lines)),),
            )
        try:
            runtime.select_model(model_name)
        except LocalRuntimeError as error:
            return OperationResult(
                "model_error", (ConsoleEvent(ConsoleEventKind.ERROR, str(error)),)
            )
        # Agent 模型会话与挂起任务必须随模型切换一起失效，避免跨模型复用旧批准语境。
        agent.clear()
        return OperationResult(
            "model",
            (
                ConsoleEvent(
                    ConsoleEventKind.COMMAND,
                    f"已选择本地模型：{runtime.selected_model}",
                ),
            ),
        )

    def status_operation() -> OperationResult:
        """以命令结果形式呈现当前模型、状态和不可突破的安全边界。"""
        snapshot = session_status()
        return OperationResult(
            "status",
            (
                ConsoleEvent(
                    ConsoleEventKind.COMMAND,
                    "\n".join(
                        (
                            f"当前模型：{snapshot.selected_model}",
                            f"运行状态：{snapshot.runtime_state}",
                            f"安全边界：{snapshot.safety_boundary}",
                        )
                    ),
                ),
            ),
        )

    def clear_session() -> None:
        """保持既有 `/clear` 展示语义，同时清除两个彼此隔离的模型上下文。"""
        runtime.clear_history()
        agent.clear()

    def dispatch(value: str, emit: EventSink | None = None) -> OperationResult:
        """分发一条输入；进度回调为空时仍可用于同步单元测试。"""
        result = dispatch_input(
            value,
            doctor=lambda: _doctor_operation(artifact_root),
            chat=chat,
            model=model_operation,
            clear=clear_session,
            status=status_operation,
            emit=emit,
        )
        if result.should_exit:
            agent.clear()
            runtime.clear_history()
        return result

    return dispatch, session_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="max-agent", description="MAX Textual local chat"
    )
    parser.add_argument(
        "--chat", action="store_true", help="Start the Textual chat interface"
    )
    commands = parser.add_subparsers(dest="command")
    doctor = commands.add_parser("doctor", help="Run local environment diagnostics")
    doctor.add_argument(
        "--artifact-root", type=Path, default=Path("artifacts"), help="Archive root"
    )
    doctor.add_argument(
        "--desktop-probe", action="store_true", help="Verify controlled desktop input"
    )
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return _doctor(args.artifact_root, desktop_probe=args.desktop_probe)
    runtime = LocalChatRuntime(_repository_root())
    dispatch, session_status = _interactive_dispatch(Path("artifacts"), runtime)
    run_textual_chat(dispatch, session_status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
