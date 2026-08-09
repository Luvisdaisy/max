# runtime-bootstrap Specification

## Purpose

Provide a repeatable, evidence-producing startup path for the Windows local development environment before any desktop automation capability is enabled.

## Requirements

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

### Requirement: Runtime capability verification
The project SHALL provide a diagnostic command that reports Python, CUDA availability, CUDA runtime version, BF16 tensor execution, required package imports, and dependency consistency in a machine-readable record.

#### Scenario: GPU-capable runtime passes verification
- **WHEN** the diagnostic command runs with the supported GPU runtime available
- **THEN** it writes an environment record containing successful CUDA and BF16 checks and exits successfully

#### Scenario: Unsupported or incomplete runtime is detected
- **WHEN** CUDA, BF16 execution, or a required dependency is unavailable
- **THEN** the diagnostic command exits non-zero and identifies the failed check without attempting desktop control or model inference

### Requirement: Safe default execution boundary
The project SHALL keep desktop input control disabled by default and SHALL not require a database, Redis, message queue, or network service to prepare or validate the first-week runtime.

#### Scenario: Fresh runtime verification
- **WHEN** a developer runs the first-week verification commands without an explicit desktop-control flag
- **THEN** no mouse or keyboard event is emitted and no infrastructure service is started

### Requirement: Doctor reports runtime and base-tool readiness
The system SHALL expose runtime verification through `/doctor` in the running Textual chat interface. It MUST NOT expose `--doctor`, `doctor`, `--diagnose`, `diagnose`, or `/diagnose` as current command aliases. Doctor SHALL check Python, required package consistency, CUDA availability, CUDA runtime, GPU identity, BF16 execution, and the readiness of mss, PyAutoGUI, OpenCV, PaddleOCR, and pynput. It SHALL present results grouped as passed, failed, and skipped while retaining a machine-readable artifact record that excludes model identity, model location, remote revision, and file-set identity.

#### Scenario: Supported Windows environment passes Doctor
- **WHEN** a developer enters `/doctor` in the Textual interface while the supported GPU runtime is available
- **THEN** it reports the Python, CUDA, GPU, BF16, and base-tool checks as passed in a readable session summary and archives the corresponding structured result

#### Scenario: A required runtime component is unavailable
- **WHEN** Doctor cannot import a required package or complete a required GPU or base-tool check
- **THEN** it reports the named check and remediation-oriented failure in both the readable session summary and artifact result without emitting desktop input

### Requirement: Explicit controlled desktop probe
The system SHALL perform screenshot, OCR, and desktop-input minimal examples only through an explicit Doctor desktop-probe option. The probe MUST use a temporary controlled test window and MUST confirm that the intended target is the Windows foreground window before input. When invoked explicitly, the probe MUST make a bounded request for its own temporary window to become foreground before that confirmation. It MUST discard captured images unless explicitly requested for ignored artifacts, and report unsupported non-interactive sessions as skipped or failed without sending input to another application. A skipped foreground check MUST state that no desktop input test was executed and how to rerun it in an interactive Windows session.

#### Scenario: Explicit probe completes in a controlled session
- **WHEN** a developer invokes Doctor with the desktop-probe option in an interactive authorized Windows session
- **THEN** Doctor verifies an in-memory screenshot, OCR against a non-sensitive test image, and the temporary window's controlled click and text-input result, then archives the outcome

#### Scenario: Foreground focus is unavailable
- **WHEN** the explicit desktop probe cannot make its temporary controlled window the Windows foreground window
- **THEN** Doctor reports the desktop probe as skipped, states that no mouse or keyboard input was emitted, explains that the interactive session must be brought to the foreground before rerunning it, and exits according to the remaining checks

#### Scenario: Default Doctor execution
- **WHEN** a developer runs Doctor without the desktop-probe option
- **THEN** Doctor performs only no-input runtime and base-tool readiness checks and identifies the desktop probe as skipped with instructions for explicit execution
