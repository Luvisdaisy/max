from __future__ import annotations

import json
from pathlib import Path

import typer

from .artifacts import ExperimentArchive
from .benchmark import run_benchmark
from .config import ModelConfig
from .console_core import OperationResult, dispatch_input
from .console_frontends import run_prompt_toolkit_console, run_textual_chat
from .diagnostics import default_probe, render_doctor, run_diagnostics
from .model_download import download_qwen35_model, run_modelscope_cli, validate_model_metadata
from .model_runtime import load_qwen35_model, require_complete_local_model
from .runtime_paths import configure_hf_modules_cache


app = typer.Typer(add_completion=False, invoke_without_command=True, no_args_is_help=False, help="Local MAX agent utilities")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _doctor(artifact_root: Path, *, desktop_probe: bool = False) -> int:
    archive = ExperimentArchive.create(artifact_root, "doctor")
    result = run_diagnostics(default_probe(desktop_probe=desktop_probe))
    archive.write_config({"command": "doctor", "desktop_probe": desktop_probe})
    archive.write_environment(result.to_dict())
    archive.append_trajectory({"event": "doctor_completed", "ok": result.ok})
    archive.write_result({"status": "success" if result.ok else "failure", "failures": result.failures})
    typer.echo(render_doctor(result))
    return 0 if result.ok else 1


def _interactive_dispatch(artifact_root: Path):
    def dispatch(value: str) -> OperationResult:
        return dispatch_input(value, doctor=lambda: OperationResult("doctor", (render_doctor(run_diagnostics(default_probe())),), exit_code=0))

    return dispatch


@app.callback()
def entry(
    ctx: typer.Context,
    artifact_root: Path = typer.Option(Path("artifacts"), "--artifact-root"),
    doctor: bool = typer.Option(False, "--doctor", help="Run Doctor and exit"),
    chat: bool = typer.Option(False, "--chat", help="Start the default chat interface"),
    fallback: bool = typer.Option(False, "--fallback", help="Start the Prompt Toolkit fallback console"),
) -> None:
    if doctor:
        raise typer.Exit(_doctor(artifact_root))
    if fallback:
        run_prompt_toolkit_console(_interactive_dispatch(artifact_root))
    elif chat or ctx.invoked_subcommand is None:
        run_textual_chat(_interactive_dispatch(artifact_root))


@app.command("doctor")
def doctor_command(
    artifact_root: Path = typer.Option(Path("artifacts"), "--artifact-root"),
    desktop_probe: bool = typer.Option(False, "--desktop-probe", help="Run controlled desktop input checks"),
) -> None:
    raise typer.Exit(_doctor(artifact_root, desktop_probe=desktop_probe))


@app.command("download-model", help="Download Qwen3.5-4B to the project model directory")
def download_model() -> None:
    typer.echo(download_qwen35_model(_repository_root(), run_modelscope_cli))


@app.command("validate-model")
def validate_model(
    model_id: str = typer.Option(..., "--model-id"),
    revision: str = typer.Option(..., "--revision"),
    model_dir: Path = typer.Option(..., "--model-dir"),
) -> None:
    from modelscope.hub.file_download import model_file_download

    metadata = validate_model_metadata(ModelConfig(model_id, revision, model_dir), _repository_root(), model_file_download)
    typer.echo(metadata)


@app.command("benchmark")
def benchmark(
    model_dir: Path = typer.Option(..., "--model-dir"),
    image: Path = typer.Option(..., "--image"),
    prompt: str = typer.Option("Describe this image.", "--prompt"),
    max_new_tokens: int = typer.Option(64, "--max-new-tokens"),
    artifact_root: Path = typer.Option(Path("artifacts"), "--artifact-root"),
) -> None:
    resolved_model_dir = require_complete_local_model(_repository_root(), model_dir)
    archive = ExperimentArchive.create(artifact_root, "benchmark")
    configure_hf_modules_cache(artifact_root)

    def infer(model: object) -> dict[str, object]:
        import torch
        from PIL import Image
        from transformers import AutoProcessor

        processor = AutoProcessor.from_pretrained(str(resolved_model_dir), local_files_only=True)
        source = Image.open(image).convert("RGB")
        messages = [{"role": "user", "content": [{"type": "image", "image": source}, {"type": "text", "text": prompt}]}]
        rendered_prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = processor(text=[rendered_prompt], images=[source], padding=True, return_tensors="pt").to("cuda")
        with torch.inference_mode():
            generated = model.generate(**inputs, max_new_tokens=max_new_tokens)
        return {"text": processor.batch_decode(generated[:, inputs.input_ids.shape[1]:], skip_special_tokens=True)[0]}

    result = run_benchmark(
        archive=archive,
        config={"model_dir": str(resolved_model_dir), "image": str(image), "prompt": prompt},
        environment=run_diagnostics(default_probe()).to_dict(),
        load_model=lambda: load_qwen35_model(resolved_model_dir),
        infer=infer,
        peak_memory_bytes=lambda: __import__("torch").cuda.max_memory_allocated(),
    )
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    app(args=argv, prog_name="max-agent")


if __name__ == "__main__":
    main()
