## Context

See `proposal.md` for motivation. The repository currently splits dependency information across `pyproject.toml` and three files below `requirements/`, while several Doctor dependencies exist only in the prepared Conda `max` environment. The target remains Windows 11, Python 3.12, NVIDIA CUDA 13.0 and local Qwen3.5 inference. PyTorch CUDA wheels require a non-default package index, and PaddleOCR/PaddlePaddle plus Windows desktop packages must coexist with the verified import order documented in `tech-design.md`.

## Goals / Non-Goals

**Goals:**

- Make root `requirements.txt` the only developer-facing dependency installation manifest.
- Allow `python -m pip install -r requirements.txt` to install pinned direct dependencies and the editable project, including the `max-agent` entry point.
- Keep the same manifest consumable by `uv pip` inside a uv-created environment and by pip inside venv or Conda environments.
- Cover all direct imports and runtime capabilities exercised by Doctor and benchmark, including CUDA PyTorch, Pillow/NumPy/OpenCV, mss, PyAutoGUI, pynput, pywinauto, PaddlePaddle and PaddleOCR.
- Remove or retire split dependency files after repository references have migrated, and prevent future manifest drift with an automated contract test.

**Non-Goals:**

- Supporting CPU-only, Linux, macOS, alternative CUDA releases or Python versions outside `>=3.12,<3.13` in this change.
- Replacing venv, uv or Conda as environment creators; the change only unifies package installation after an environment exists.
- Generating a transitive hash lock for every wheel. Exact direct-version pins are required now; a fully hashed cross-index lock remains a later release-hardening task.
- Changing Agent, Doctor, model benchmark or desktop-control behavior.

## Decisions

### 1. Root manifest contains the complete install and the editable project

`requirements.txt` will contain exact direct dependency pins, the PyTorch CUDA 13.0 extra index directive, and `-e .`. Consequently, the single documented command installs both third-party packages and the local `max-desktop-agent` command entry point.

Alternative considered: keep `python -m pip install -e .` as a second command. This would leave dependency installation uniform but would not satisfy the requested one-command setup and would make it easier to forget command registration.

### 2. Use a pip-compatible extra index directive

The manifest will use `--extra-index-url https://download.pytorch.org/whl/cu130` with the exact `torch==2.13.0+cu130` and `torchvision==0.28.0+cu130` pins. Packages without the `+cu130` build continue to resolve from PyPI, while the CUDA pins select the intended PyTorch wheels. The implementation will validate both pip and `uv pip` parsing.

Alternative considered: retain `requirements/torch-cu130.txt` with `--index-url`. That preserves strict index separation but violates the single-manifest requirement and requires multiple installation commands.

### 3. Pin direct dependencies from verified runtime roles

The root manifest will explicitly cover these groups:

- application and orchestration: LangChain, LangGraph, ModelScope, Transformers, Typer, Rich, Prompt Toolkit and Textual;
- model and image runtime: PyTorch, TorchVision, Pillow, NumPy and OpenCV;
- desktop and perception checks: mss, PyAutoGUI, pynput and pywinauto;
- OCR and contracts: PaddlePaddle, PaddleOCR and Pydantic.

Transitive packages such as PaddleX or `comtypes` remain resolver-managed unless project code imports them directly. Direct pins will match the currently verified `max` environment before validation.

### 4. Remove split dependency manifests after reference migration

`requirements/base.txt`, `requirements/constraints.txt` and `requirements/torch-cu130.txt` will be deleted once all repository documentation and tests reference the root manifest. `pyproject.toml` remains necessary for package metadata and build configuration; its application dependencies may overlap with the root manifest, but it is no longer presented as a complete development-runtime installer.

Alternative considered: keep the old files as generated subsets. No generator currently exists, so retaining them would create multiple manually maintained dependency truths.

### 5. Validate the contract without rebuilding every environment in unit tests

A focused test will parse `requirements.txt` and assert the extra index, editable project entry and required direct packages. Normal verification will run `pip check`, all unit tests and CLI help in the current supported environment. A real `pip install -r requirements.txt` resolver/install check will also be performed during apply; venv, uv and Conda commands will be documented, while full clean-environment installation remains a manual release verification because it downloads large CUDA/OCR artifacts.

## Risks / Trade-offs

- **Extra-index dependency confusion or resolver differences** → exact direct pins limit candidate selection; validate with both pip and uv parsing, and keep the trusted PyTorch URL explicit.
- **Large installation size and download time** → document the Windows/CUDA scope and avoid pretending this is a lightweight CPU environment.
- **PaddlePaddle or OCR wheel availability changes** → pin the verified versions and fail visibly instead of adding fallback branches.
- **Duplicate pins between `pyproject.toml` and `requirements.txt`** → treat the root file as the complete developer entry point and add a contract test for required packages; package metadata remains independently useful for tooling.
- **`-e .` depends on the current working directory** → documentation requires running the command from the repository root, which is already the project convention.

## Migration Plan

1. Create root `requirements.txt` from versions verified in Conda `max`, including the PyTorch extra index and `-e .`.
2. Add a dependency-manifest contract test and update all repository references to the root file.
3. Delete the three superseded files below `requirements/` after confirming no references remain.
4. Run installation/resolution in the supported environment, followed by `pip check`, all unit tests, CLI help and Doctor as appropriate for the interactive session.
5. Roll back by restoring the deleted split manifests and previous documentation if the unified resolver cannot install the verified Windows/CUDA combination.
