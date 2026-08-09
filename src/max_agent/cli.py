from __future__ import annotations

import argparse
from pathlib import Path

from .artifacts import ExperimentArchive
from .console_core import OperationResult, dispatch_input
from .console_frontends import run_textual_chat
from .diagnostics import default_probe, render_doctor, run_diagnostics
from .local_llm import LocalChatRuntime


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
    def dispatch(value: str) -> OperationResult:
        return dispatch_input(
            value, doctor=lambda: _doctor_operation(artifact_root), chat=runtime.reply
        )

    return dispatch


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="max-agent", description="MAX Textual local chat"
    )
    parser.add_argument(
        "--chat", action="store_true", help="Start the Textual chat interface"
    )
    parser.parse_args(argv)
    runtime = LocalChatRuntime(_repository_root())
    run_textual_chat(_interactive_dispatch(Path("artifacts"), runtime))


if __name__ == "__main__":
    main()
