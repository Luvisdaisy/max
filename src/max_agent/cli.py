from __future__ import annotations

import argparse
import json
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
from .orchestration.tool_calling import ReadOnlyToolExplainer, ToolSelectionError
from .tools.registry import build_default_registry


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


def _interactive_dispatch(artifact_root: Path, runtime: LocalChatRuntime):
    """组装 UI 无关的本地聊天分发器，并只发布经过净化的进度事件。"""
    registry = build_default_registry()

    def session_status() -> SessionStatus:
        """返回状态栏与 `/status` 命令共享的只读快照。"""
        return SessionStatus(runtime.selected_model, runtime.state)

    def chat(goal: str, emit: EventSink) -> str:
        """完成一次可选只读工具循环，并将阶段状态报告给前端。"""

        def report_runtime_state(state: str) -> None:
            labels = {
                "loading": "正在加载本地模型",
                "generating": "正在生成本地回复",
                "ready": "本地会话就绪",
                "failed": "本地运行时失败",
            }
            emit(
                ConsoleEvent(
                    ConsoleEventKind.NOTICE,
                    labels.get(state, state),
                    state=state,
                )
            )

        def select(
            user_goal: str, tools: tuple[dict[str, object], ...]
        ) -> dict[str, object]:
            prompt = (
                "Return only JSON with tool_name and arguments. Choose at most one "
                "read-only tool when it is needed to answer the user; otherwise return "
                f'{{"tool_name": null}}. User goal: {user_goal}. Tools: {json.dumps(tools)}'
            )
            try:
                response = runtime.reply(prompt, report_runtime_state)
                return json.JSONDecoder().raw_decode(response[response.find("{") :])[0]
            except json.JSONDecodeError as error:
                raise ToolSelectionError(
                    "model returned an invalid tool selection"
                ) from error

        def explain(user_goal: str, observation: dict[str, object]) -> str:
            failure = observation.get("tool_failure")
            if failure is not None:
                # 最终提示只携带工具层生成的白名单观察；要求先回应用户，且禁止递归工具调用。
                prompt = "\n".join(
                    (
                        "继续回答用户的原始消息。一次只读工具尝试失败，但这不是对话终点。",
                        "请理解净化后的失败原因，优先完成用户原始意图；必要时简要说明能力限制。",
                        "不得请求或调用第二个工具，不得猜测未提供的参数、回执或异常细节。",
                        f"用户原始消息：{user_goal}",
                        f"净化失败观察：{json.dumps(failure, ensure_ascii=False)}",
                    )
                )
                return runtime.reply(prompt, report_runtime_state)
            image = observation.get("image")
            return (
                runtime.explain_image(user_goal, image, report_runtime_state)
                if image is not None
                else runtime.reply(user_goal, report_runtime_state)
            )

        return (
            ReadOnlyToolExplainer(
                registry,
                select,
                explain,
                on_tool_event=lambda name, state, elapsed: emit(
                    ConsoleEvent.tool(name, state, elapsed)
                ),
            )
            .run(goal)
            .text
        )

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

    def dispatch(value: str, emit: EventSink | None = None) -> OperationResult:
        """分发一条输入；进度回调为空时仍可用于同步单元测试。"""
        return dispatch_input(
            value,
            doctor=lambda: _doctor_operation(artifact_root),
            chat=chat,
            model=model_operation,
            clear=runtime.clear_history,
            status=status_operation,
            emit=emit,
        )

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
