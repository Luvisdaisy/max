from __future__ import annotations

import argparse
import json
from pathlib import Path

from .artifacts import ExperimentArchive
from .console_core import OperationResult, dispatch_input
from .console_frontends import run_textual_chat
from .diagnostics import default_probe, render_doctor, run_diagnostics
from .local_llm import LocalChatRuntime, LocalRuntimeError
from .orchestration.tool_calling import ReadOnlyToolExplainer
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
        "doctor", (render_doctor(result),), exit_code=0 if result.ok else 1
    )


def _doctor(artifact_root: Path, *, desktop_probe: bool = False) -> int:
    operation = _doctor_operation(artifact_root, desktop_probe=desktop_probe)
    print(*operation.messages, sep="\n")
    return operation.exit_code


def _interactive_dispatch(artifact_root: Path, runtime: LocalChatRuntime):
    registry = build_default_registry()

    def chat(goal: str) -> str:
        def select(
            user_goal: str, tools: tuple[dict[str, object], ...]
        ) -> dict[str, object]:
            prompt = (
                "Return only JSON with tool_name and arguments. Choose at most one "
                "read-only tool when it is needed to answer the user; otherwise return "
                f'{{"tool_name": null}}. User goal: {user_goal}. Tools: {json.dumps(tools)}'
            )
            try:
                response = runtime.reply(prompt)
                return json.JSONDecoder().raw_decode(response[response.find("{") :])[0]
            except json.JSONDecodeError as error:
                raise RuntimeError(
                    "model returned an invalid tool selection"
                ) from error

        def explain(user_goal: str, observation: dict[str, object]) -> str:
            image = observation.get("image")
            return (
                runtime.explain_image(user_goal, image)
                if image is not None
                else runtime.reply(user_goal)
            )

        return ReadOnlyToolExplainer(registry, select, explain).run(goal).text

    def model_operation(model_name: str | None) -> OperationResult:
        if model_name is None:
            models = runtime.available_models()
            if not models:
                return OperationResult("model", ("未发现可选择的本地模型。",))
            lines = ["可选本地模型："]
            lines.extend(
                f"{'* ' if name == runtime.selected_model else '  '}{name}"
                for name in models
            )
            lines.append("使用 /model <模型目录> 切换模型。")
            return OperationResult("model", tuple(lines))
        try:
            runtime.select_model(model_name)
        except LocalRuntimeError as error:
            return OperationResult("model_error", (str(error),))
        return OperationResult("model", (f"已选择本地模型：{runtime.selected_model}",))

    def dispatch(value: str) -> OperationResult:
        return dispatch_input(
            value,
            doctor=lambda: _doctor_operation(artifact_root),
            chat=chat,
            model=model_operation,
        )

    return dispatch


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
    run_textual_chat(_interactive_dispatch(Path("artifacts"), runtime))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
