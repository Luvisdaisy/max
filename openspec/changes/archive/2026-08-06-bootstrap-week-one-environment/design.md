## Context

See proposal.md for motivation. The repository currently contains planning material but no application package. The target is Windows 11 with the user-managed Conda `max` environment, Python 3.12, an RTX 5070 Ti, and PyTorch CUDA 13.0. Model weights live under the repository's Git-ignored `model/` tree, while reproducibility evidence belongs in an ignored `artifacts/` tree.

## Goals / Non-Goals

**Goals:**

- Create a small import-safe Python package and a single CLI surface for environment checks, model acquisition, and local benchmarking.
- Make external paths explicit; record enough structured evidence to reproduce or diagnose a run.
- Establish stable configuration and model-provider interfaces for later perception and Agent work.

**Non-Goals:**

- Implement OCR, UI Automation, mouse/keyboard control, LangGraph execution, a GUI, training, multi-agent coordination, or network infrastructure.
- Download model weights during tests or commit models, screenshots, credentials, or run output.

## Decisions

### Python src layout with a narrow CLI

Use a `src/` package layout with a CLI that dispatches environment diagnostics, model download, and benchmark commands. Keep configuration and provider protocols separate from command handlers so Week 2–4 modules can import them without coupling to CLI parsing.

Alternative considered: a collection of top-level scripts. Rejected because import boundaries and testability degrade as perception and orchestration are added.

### Declarative, pinned dependencies with layered installation guidance

Keep project metadata and locked dependencies in the repository, while documenting the CUDA-specific PyTorch index separately from ordinary package installation. The diagnostic command remains the authority that verifies the installed result, rather than assuming a successful installer implies GPU support.

Alternative considered: use unpinned requirements. Rejected because the first benchmark must be reproducible across reinstalls.

### Project-local Git-ignored model directory and offline loading

All model commands resolve their storage below the repository-root `model/` directory. The first verification model is `Qwen/Qwen3.5-4B`, downloaded with `modelscope download --model Qwen/Qwen3.5-4B --local_dir <repo>/model/Qwen/Qwen3.5-4B`; the download workflow records the resolved revision. Benchmark uses Qwen's native Transformers multimodal loader with `local_files_only` semantics and never performs an implicit network fetch. The existing GLM model remains available only for a later, separately tracked compatibility evaluation because its remote-code runtime is not compatible with the currently verified Transformers environment.

Alternative considered: use a repository-external cache. Rejected because this project requires all downloaded models to remain in a single project-local directory. Framework defaults are also rejected because they make location and provenance unclear.

### JSON evidence bundle per run

Each command creates or updates an ignored run directory containing `config.yaml`, `environment.json`, `trajectory.jsonl`, and `result.json`; screenshots are optional and remain untracked. Failures after run initialization write a failure result with diagnostics.

Alternative considered: console-only output. Rejected because it cannot support latency comparisons, incident diagnosis, or later audit requirements.

### Safe-by-default boundary

The initial CLI contains no desktop-control command. Future input control must be opt-in through an explicit `--enable-desktop-control` flag and protected by its own Guard and session-lock design.

Alternative considered: expose controller primitives now. Rejected because importing them into a bootstrap environment expands the risk surface before the safety controls exist.

## Risks / Trade-offs

- [CUDA/PyTorch mismatch yields a CPU-only environment] → Verify CUDA version and perform a real BF16 CUDA tensor operation, not merely package imports.
- [3B BF16 model exceeds latency or memory budget] → Capture peak memory and timing; reduce image size, output length, and context before considering quantization.
- [ModelScope download is incomplete or the resolved revision changes] → Validate small metadata first, record the resolved revision, and make the benchmark offline-only.
- [Project-local model directory is accidentally committed] → Ignore `model/`, reject alternate targets, and review Git status before commits.
- [PaddleOCR and PyTorch DLL ordering conflicts] → Do not initialize OCR in Week 1; document the later ordering constraint.
- [Evidence includes sensitive data] → Default to synthetic inputs, avoid screenshots unless explicitly supplied, and keep artifacts ignored.

## Migration Plan

1. Add the package skeleton, project metadata, ignored artifact policy, documentation, and test scaffolding.
2. Add deterministic environment diagnostics and verify them in the target Conda environment.
3. Add project-local `model/` download and offline single-image benchmark commands using a non-sensitive fixture.
4. Record the initial baseline; rollback consists of removing the newly introduced package and project files, with no persistent service or data migration to reverse.
