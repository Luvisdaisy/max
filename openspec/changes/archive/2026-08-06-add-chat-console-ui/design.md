## Context

See proposal.md for motivation. The current package exposes diagnostics, model download, metadata validation, and benchmark actions through an argparse adapter. These actions already produce structured evidence and must remain independent of terminal UI rendering. The new dependency set introduces Typer, Rich, Prompt Toolkit, and Textual while AI inference and desktop control remain unavailable from the console.

## Goals / Non-Goals

**Goals:**

- Establish a shared command-dispatch boundary that can be invoked by one-line CLI, Textual, and Prompt Toolkit frontends.
- Make the default experience a chat transcript with slash commands and honest placeholder responses before a chat backend exists.
- Preserve deterministic, non-interactive diagnostic exit behavior and the existing operational commands.

**Non-Goals:**

- Implement LLM conversation, streaming tokens, model selection, tool calling, desktop control, persistent conversation history, a web UI, or a native Windows GUI.
- Remove or alter the semantics of the current model download, validation, and benchmark workflows.

## Decisions

### Single operation core with presentation adapters

Represent user operations as a small command result contract containing output events and an exit status. Typer routes one-line arguments to this core; Textual and Prompt Toolkit render the same results in their respective interaction models. This prevents diagnostic semantics from being duplicated in UI callbacks.

Alternative considered: allow each frontend to call diagnostic and benchmark modules directly. Rejected because command behavior, error rendering, and future AI tool dispatch would diverge.

### Textual is the default interactive frontend; Prompt Toolkit is explicit fallback

`max-agent` and `max-agent --chat` select Textual when an interactive terminal is available. A dedicated fallback mode selects Prompt Toolkit for constrained terminals. The fallback is explicit rather than silently changing interaction modes, so developers can reproduce UI issues and understand which frontend is active.

Alternative considered: use Prompt Toolkit only. Rejected because it does not establish the chat transcript and status layout needed by the future GUI Agent development framework.

### Typer owns public command syntax; Rich owns portable formatting

Typer defines the public CLI, including `--diagnose`, `--chat`, and compatibility aliases for existing operations. Rich supplies consistent human-readable output for one-line and fallback flows. Existing structured evidence files remain the authoritative machine-readable records.

Alternative considered: retain argparse and layer UI frameworks around it. Rejected because Typer provides a clearer typed command tree and avoids maintaining two CLI parsing systems.

### Honest local chat placeholder

Ordinary text is appended as a user message and receives a fixed local backend-not-configured response. Slash commands are parsed before chat messages. The placeholder deliberately makes no network request and never attempts to load a local model.

Alternative considered: automatically load Qwen for chat. Rejected because it changes startup cost, GPU ownership, and safety scope before an AI session design exists.

## Risks / Trade-offs

- [Textual cannot initialize on a terminal] → Provide an explicit Prompt Toolkit fallback and test the shared dispatcher without either UI runtime.
- [Typer syntax breaks an existing script] → Test `--diagnose`, `--chat`, and retained development-operation aliases as compatibility contracts.
- [UI callbacks duplicate business logic] → Keep all operation execution behind the command result contract.
- [A placeholder looks like an AI answer] → Use an explicit system-style message stating that no AI backend is configured.
- [Terminal dependencies add import cost] → Import Textual and Prompt Toolkit only inside the selected frontend entry point.

## Migration Plan

1. Add dependencies and introduce the command-core contract alongside the existing modules.
2. Replace the argparse adapter with Typer routing while retaining current operations and adding compatibility tests.
3. Add Prompt Toolkit fallback and Textual chat interface on top of the shared dispatcher.
4. Document interactive and one-line usage; rollback consists of restoring the previous CLI adapter and removing the new dependencies, with no persisted data migration.
