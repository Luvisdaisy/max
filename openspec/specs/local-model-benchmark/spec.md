# local-model-benchmark Specification

## Purpose

Provide a repeatable local model acquisition and single-image benchmark workflow whose evidence can be inspected without committing model weights or private runtime data.

## Requirements

### Requirement: Project-local ignored model directory
The project SHALL store every downloaded model under the repository-root `model/` directory and SHALL exclude that directory and its contents from version control.

#### Scenario: Qwen model download uses the project model directory
- **WHEN** a developer downloads `Qwen/Qwen3.5-4B`
- **THEN** the downloader stores it below `model/Qwen/Qwen3.5-4B` and records the selected model identity and resolved revision

#### Scenario: Download target is outside the project model directory
- **WHEN** a developer supplies a model destination outside the repository-root `model/` directory
- **THEN** the command fails before downloading model files and explains the required project-local destination

### Requirement: Offline local benchmark
The project SHALL provide a benchmark command that loads an already-downloaded local model without network access and records load time, peak GPU memory, inference latency, configuration, and result status for one input image. Before loading, the command SHALL perform the local preflight required by this capability. The command MUST reject a model directory outside the repository-root `model/` directory or a model other than the supported Qwen3.5-4B target.

#### Scenario: Completed local benchmark
- **WHEN** a complete supported model is present in the configured project-local model directory and a readable local input image is supplied
- **THEN** the benchmark runs without downloading additional files and writes the required evidence records to an ignored artifact directory

#### Scenario: Missing local model files
- **WHEN** the configured model files are incomplete or unavailable locally
- **THEN** the benchmark fails with a clear remediation message and does not fall back to a network download

#### Scenario: Unsupported model location or identity
- **WHEN** a developer supplies a model directory outside the project-local supported Qwen3.5-4B destination
- **THEN** the benchmark rejects the request before model loading and explains the required project-local destination

### Requirement: Reproducible experiment archive
The benchmark workflow SHALL produce configuration, environment, trajectory, result, and optional screenshot records for each run, while excluding model weights, private input data, secrets, and absolute local paths from version control. The workflow MUST write a structured failure result and trajectory event for every failure that occurs after archive creation.

#### Scenario: Archived benchmark evidence
- **WHEN** a benchmark run completes or fails after initialization
- **THEN** the run directory contains the applicable structured records needed to diagnose the outcome without containing model weights, private input data, secrets, or absolute local paths

### Requirement: Offline benchmark preflight
Before loading a model, the system SHALL validate that the requested model directory is the supported project-local Qwen3.5-4B directory, that it contains the minimum files required for local inference, and that the supplied image is a readable image file. A failed preflight MUST identify the failing input and a local remediation action, and MUST NOT initiate a network request or model download.

#### Scenario: Valid local inputs pass preflight
- **WHEN** a developer supplies the supported complete local Qwen3.5-4B directory and a readable image
- **THEN** the benchmark proceeds to load the model without resolving remote model resources

#### Scenario: Local model is incomplete
- **WHEN** the requested project-local model directory lacks a required inference file
- **THEN** the command fails before model loading, identifies the missing local prerequisite, and does not download any file

#### Scenario: Image input is invalid
- **WHEN** the supplied image path is missing or cannot be decoded as an image
- **THEN** the command fails before model loading with an input-specific remediation message and does not download any file

### Requirement: Offline benchmark acceptance evidence
The system SHALL record an offline benchmark's selected runtime parameters, explicit offline execution state, model-load duration, peak GPU-memory value, inference duration, and final status in the run archive. The archive MUST NOT contain model weights, image content, or absolute model or image paths.

#### Scenario: Offline benchmark completes
- **WHEN** a supported complete local model and readable image are benchmarked successfully
- **THEN** the archive contains the required non-sensitive configuration, environment, trajectory, and success result records for that run

#### Scenario: Benchmark fails after archive creation
- **WHEN** preflight, model loading, or inference fails after the benchmark archive is created
- **THEN** the archive contains a failure result and a trajectory event identifying the failed stage without exposing model weights, image content, or absolute input paths
