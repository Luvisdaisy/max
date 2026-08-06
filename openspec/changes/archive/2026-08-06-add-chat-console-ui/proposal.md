## Why

The prototype currently exposes useful local operations only through isolated argparse subcommands. A chat-first console is needed now to establish the interaction surface for the future GUI Agent while keeping diagnostics and model tooling directly accessible to developers.

## What Changes

- Add a chat-first Textual terminal UI that opens by default and provides a conversation transcript, command input, status feedback, and graceful exit.
- Add a Prompt Toolkit REPL fallback for terminals that cannot run the Textual interface.
- Introduce a Typer command surface that supports both interactive entry points and non-interactive one-line operations, including `max-agent --diagnose` and `max-agent --chat`.
- Expose `/diagnose` and `/quit` from both interactive frontends by dispatching to the same command core as non-interactive execution.
- Display a clear local placeholder when a user sends a chat message before an AI backend has been configured; no model response is fabricated.

## Capabilities

### New Capabilities
- `chat-console-ui`: A chat-first terminal interface, portable interactive fallback, and shared command dispatch contract for the local GUI Agent development framework.

### Modified Capabilities

None.

## Impact

- Adds pinned `typer`, `rich`, `prompt_toolkit`, and `textual` dependencies.
- Replaces the current argparse-only CLI adapter while preserving existing diagnose, model download, metadata validation, and benchmark operations through a shared command core.
- Adds UI, console-dispatch, and command compatibility tests; no desktop control, AI inference backend, network service, or model download is introduced.
