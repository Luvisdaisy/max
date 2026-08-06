## Purpose

Provide a repeatable, evidence-producing startup path for the Windows local development environment before any desktop automation capability is enabled.

## ADDED Requirements

### Requirement: Reproducible runtime setup
The project SHALL document the supported Conda environment, Python version, pinned dependency sources, and the command sequence required to prepare the runtime on a Windows development machine.

#### Scenario: Developer prepares a supported environment
- **WHEN** a developer follows the environment setup documentation on a supported machine
- **THEN** they can identify the required Conda environment, interpreter version, package sources, and lock material without relying on implicit global packages

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
