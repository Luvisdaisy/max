## MODIFIED Requirements

### Requirement: Reproducible runtime setup
The project SHALL provide one root-level `requirements.txt` as the complete developer installation entry point for all direct Python dependencies required by the CLI, Doctor, local model benchmark, desktop-tool checks, Windows UI Automation, and OCR runtime. The manifest MUST pin dependency versions, declare the package index needed by the supported CUDA build, and install the project command entry point when a developer runs `python -m pip install -r requirements.txt`. The same manifest SHALL be consumable through pip in a Python 3.12 venv or Conda environment and through `uv pip`; setup documentation MUST describe environment creation separately from this shared dependency installation step and MUST NOT rely on implicit global packages or a pre-populated Conda environment.

#### Scenario: Developer prepares a supported environment
- **WHEN** a developer follows the environment setup documentation on a supported Windows machine
- **THEN** they can create or select a Python 3.12 environment, install the project and all required dependencies from the root `requirements.txt`, run Doctor, and identify evidence locations without relying on implicit global packages

#### Scenario: Install into a Python venv with pip
- **WHEN** a developer activates a supported Python 3.12 venv and runs `python -m pip install -r requirements.txt`
- **THEN** pip installs the project command and all pinned dependencies required to run the documented Doctor and local benchmark workflows without consulting another requirements file

#### Scenario: Install into a Conda environment with pip
- **WHEN** a developer creates or activates any supported Python 3.12 Conda environment and runs `python -m pip install -r requirements.txt`
- **THEN** the environment receives the same project and dependency versions as the supported venv workflow without requiring the environment to be named `max`

#### Scenario: Install through uv
- **WHEN** a developer creates or selects a supported Python 3.12 environment and runs `uv pip install -r requirements.txt`
- **THEN** uv consumes the same root manifest, including the supported CUDA package source, and installs the same direct dependency set and project command entry point

#### Scenario: Verify the installed runtime
- **WHEN** installation from the root manifest completes on a supported Windows machine
- **THEN** the developer can run `python -m pip check`, the automated tests, `max-agent --help`, and Doctor using only packages declared by that installation workflow

#### Scenario: Consult setup documentation
- **WHEN** a developer reads the runtime setup documentation
- **THEN** the documentation identifies the supported Python and platform constraints, shows the pip, uv, and Conda environment variants, uses only the root `requirements.txt` as the dependency manifest, and identifies Doctor evidence locations without recording model identity
