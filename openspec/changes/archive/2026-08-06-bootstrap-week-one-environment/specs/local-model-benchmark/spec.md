## Purpose

Provide a repeatable local model acquisition and single-image benchmark workflow whose evidence can be inspected without committing model weights or private runtime data.

## ADDED Requirements

### Requirement: Project-local ignored model directory
The project SHALL store every downloaded model under the repository-root `model/` directory and SHALL exclude that directory and its contents from version control.

#### Scenario: Qwen model download uses the project model directory
- **WHEN** a developer downloads `Qwen/Qwen3.5-4B`
- **THEN** the downloader stores it below `model/Qwen/Qwen3.5-4B` and records the selected model identity and resolved revision

#### Scenario: Download target is outside the project model directory
- **WHEN** a developer supplies a model destination outside the repository-root `model/` directory
- **THEN** the command fails before downloading model files and explains the required project-local destination

### Requirement: Offline local benchmark
The project SHALL provide a benchmark command that loads an already-downloaded local model without network access and records load time, peak GPU memory, inference latency, configuration, and result status for one input image.

#### Scenario: Completed local benchmark
- **WHEN** a complete supported model is present in the configured project-local model directory
- **THEN** the benchmark runs without downloading additional files and writes the required evidence records to an ignored artifact directory

#### Scenario: Missing local model files
- **WHEN** the configured model files are incomplete or unavailable locally
- **THEN** the benchmark fails with a clear remediation message and does not fall back to a network download

### Requirement: Reproducible experiment archive
The benchmark workflow SHALL produce configuration, environment, trajectory, result, and optional screenshot records for each run, while excluding model weights, private input data, and secrets from version control.

#### Scenario: Archived benchmark evidence
- **WHEN** a benchmark run completes or fails after initialization
- **THEN** the run directory contains the applicable structured records needed to diagnose the outcome
