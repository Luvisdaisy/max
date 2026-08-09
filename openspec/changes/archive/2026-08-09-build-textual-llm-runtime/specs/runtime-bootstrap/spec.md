## MODIFIED Requirements

### Requirement: Doctor reports runtime and base-tool readiness
The system SHALL expose runtime verification through `/doctor` in the running Textual chat interface. It MUST NOT expose `--doctor`, `doctor`, `--diagnose`, `diagnose`, or `/diagnose` as current command aliases. Doctor SHALL check Python, required package consistency, CUDA availability, CUDA runtime, GPU identity, BF16 execution, and the readiness of mss, PyAutoGUI, OpenCV, PaddleOCR, and pynput. It SHALL present results grouped as passed, failed, and skipped while retaining a machine-readable artifact record that excludes model identity, model location, remote revision, and file-set identity.

#### Scenario: Supported Windows environment passes Doctor
- **WHEN** a developer enters `/doctor` in the Textual interface while the supported GPU runtime is available
- **THEN** it reports the Python, CUDA, GPU, BF16, and base-tool checks as passed in a readable session summary and archives the corresponding structured result

#### Scenario: A required runtime component is unavailable
- **WHEN** Doctor cannot import a required package or complete a required GPU or base-tool check
- **THEN** it reports the named check and remediation-oriented failure in both the readable session summary and artifact result without emitting desktop input
