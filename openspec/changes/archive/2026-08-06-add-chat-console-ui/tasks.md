## 1. Command-core foundation

- [x] 1.1 Add pinned Typer, Rich, Prompt Toolkit, and Textual dependencies with installation guidance.
- [x] 1.2 Define a UI-independent operation result and dispatcher for chat text, slash commands, and existing diagnostics.
- [x] 1.3 Add unit tests for `/diagnose`, `/quit`, unsupported slash commands, and the no-backend chat placeholder.

## 2. One-line CLI compatibility

- [x] 2.1 Replace the argparse-only entry adapter with a Typer command surface that preserves diagnose, model download, validation, and benchmark operations.
- [x] 2.2 Add `max-agent --diagnose` and `max-agent --chat` one-line entry points with deterministic exit behavior.
- [x] 2.3 Add CLI compatibility tests for the new flags and retained development-operation aliases.

## 3. Interactive frontends

- [x] 3.1 Implement the Prompt Toolkit fallback REPL with command history and shared dispatcher rendering.
- [x] 3.2 Implement the default Textual chat interface with transcript, input, status feedback, `/diagnose`, `/quit`, and placeholder message rendering.
- [x] 3.3 Add frontend tests that exercise shared command behavior without requiring an interactive terminal or model inference.

## 4. Documentation and verification

- [x] 4.1 Document default chat, fallback console, and one-line command usage, including the current no-backend limitation.
- [x] 4.2 Run the automated test suite and perform a manual Textual and Prompt Toolkit smoke test without enabling desktop control or model inference.
