## MODIFIED Requirements

### Requirement: Reproducible runtime setup
The project SHALL document the supported Conda environment, Python version, pinned dependency sources, and the command sequence required to prepare and verify the runtime on a Windows development machine. The documentation MUST describe the `doctor` verification command and its evidence location without requiring, identifying, or recording any model.

#### Scenario: Developer prepares a supported environment
- **WHEN** a developer follows the environment setup documentation on a supported machine
- **THEN** they can identify the required Conda environment, interpreter version, package sources, verification order, Doctor command, and evidence locations without relying on implicit global packages

## ADDED Requirements

### Requirement: Doctor reports runtime and base-tool readiness
The system SHALL expose runtime verification through `--doctor`, `doctor`, and `/doctor`; it MUST NOT expose `--diagnose`, `diagnose`, or `/diagnose` as current command aliases. Doctor SHALL check Python, required package consistency, CUDA availability, CUDA runtime, GPU identity, BF16 execution, and the readiness of mss, PyAutoGUI, OpenCV, PaddleOCR, and pynput. It SHALL present results grouped as passed, failed, and skipped while retaining a machine-readable artifact record that excludes model identity, model location, remote revision, and file-set identity.

#### Scenario: Supported Windows environment passes Doctor
- **WHEN** Doctor runs in the supported Conda environment on a Windows machine with the required GPU and base tools installed
- **THEN** it reports the Python, CUDA, GPU, BF16, and base-tool checks as passed in a readable summary and archives the corresponding structured result

#### Scenario: A required runtime component is unavailable
- **WHEN** Doctor cannot import a required package or complete a required GPU or base-tool check
- **THEN** it reports the named check and remediation-oriented failure in both the readable summary and artifact result, and exits non-zero without emitting desktop input

### Requirement: Explicit controlled desktop probe
The system SHALL perform screenshot, OCR, and desktop-input minimal examples only through an explicit Doctor desktop-probe option. The probe MUST use a temporary controlled test window, confirm that the intended target is available before input, discard captured images unless explicitly requested for ignored artifacts, and report unsupported non-interactive sessions as skipped or failed without sending input to another application.

#### Scenario: Explicit probe completes in a controlled session
- **WHEN** a developer invokes Doctor with the desktop-probe option in an interactive authorized Windows session
- **THEN** Doctor verifies an in-memory screenshot, OCR against a non-sensitive test image, and the temporary window's controlled click and text-input result, then archives the outcome

#### Scenario: Default Doctor execution
- **WHEN** a developer runs Doctor without the desktop-probe option
- **THEN** Doctor performs only no-input runtime and base-tool readiness checks and identifies the desktop probe as skipped with instructions for explicit execution
