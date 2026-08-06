## 1. Project foundation

- [x] 1.1 Create the `src/` Python package layout, import-safe package boundary, and a narrow CLI command structure for diagnostics, download, and benchmark operations.
- [x] 1.2 Add pinned project metadata, dependency lock material, and installation guidance that separates the CUDA 13.0 PyTorch source from ordinary Python packages.
- [x] 1.3 Update `.gitignore` and the artifact-directory convention so the repository-root `model/` directory, screenshots, run output, generated COM files, secrets, and local caches are excluded.
- [x] 1.4 Define typed runtime configuration and model-provider interfaces without implementing desktop control, OCR, or LangGraph execution.

## 2. Runtime verification

- [x] 2.1 Implement a machine-readable environment diagnostic command for Python, package imports, CUDA availability, CUDA runtime version, and dependency consistency.
- [x] 2.2 Implement a real CUDA BF16 tensor-operation check with explicit non-zero failure behavior for unsupported or incomplete environments.
- [x] 2.3 Write environment setup and verification documentation for the `max` Conda environment, including safe no-desktop-control defaults.
- [x] 2.4 Add unit tests for diagnostic result serialization and failure reporting using mocked hardware/library probes.

## 3. External model cache and evidence archive

- [x] 3.1 Replace external-cache validation with repository-root `model/` directory validation; reject all other model destinations and record the selected model identifier and resolved revision.
- [x] 3.2 Update the explicit ModelScope downloader to validate small metadata and download `Qwen/Qwen3.5-4B` to `model/Qwen/Qwen3.5-4B` with `modelscope download --model Qwen/Qwen3.5-4B --local_dir <repo>/model/Qwen/Qwen3.5-4B`.
- [x] 3.3 Implement ignored run-directory creation and structured `config.yaml`, `environment.json`, `trajectory.jsonl`, and `result.json` records for success and post-initialization failure paths.
- [x] 3.4 Update unit tests for path validation, Qwen model-download request construction, and evidence-bundle failure handling without network access.

## 4. Offline single-image benchmark

- [x] 4.1 Update the offline-only local-model loader to require a complete model below the repository-root `model/` directory, fail clearly when files are absent, and never fall back to network retrieval.
- [x] 4.2 Implement the Qwen3.5-4B single-image BF16 benchmark command with load-time, peak-GPU-memory, inference-latency, configuration, and result-status recording.
- [x] 4.3 Update the non-sensitive fixture and tests to exercise Qwen benchmark configuration and missing-model behavior without downloading weights or performing a real GPU inference.

## 5. Verification and first baseline

- [x] 5.1 Run the diagnostic command in the target `max` environment and archive the resulting environment record outside version control.
- [ ] 5.2 Inventory the existing `Qwen/Qwen3.5-4B` download at `F:\Coding\max\model\Qwen\Qwen3.5-4B` and archive the resolved revision.
- [x] 5.3 Run one offline single-image BF16 baseline with the downloaded Qwen model and archive its evidence bundle, including load time, peak memory, and latency.
- [x] 5.4 Run the automated test suite and document the reproducible commands and observed baseline in the environment documentation.
