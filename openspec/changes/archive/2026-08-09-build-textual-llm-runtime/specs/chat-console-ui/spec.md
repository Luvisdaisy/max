## MODIFIED Requirements

### Requirement: Default chat-first terminal interface
The application SHALL provide a Textual terminal interface as its only interactive experience, with visible chat history, input, loading and error status, and a graceful exit action. `max-agent` and `max-agent --chat` SHALL start the same Textual interface. Ordinary text SHALL be sent to the local LLM runtime rather than receiving a fabricated unconfigured-backend message.

#### Scenario: Start the default interface
- **WHEN** a developer starts `max-agent` in an interactive terminal
- **THEN** the application opens the Textual chat interface and accepts ordinary text and supported slash commands

#### Scenario: Start the explicit chat interface
- **WHEN** a developer runs `max-agent --chat`
- **THEN** the application starts the same Textual chat interface used by the default entry point

#### Scenario: Send chat text before an AI backend exists
- **WHEN** a developer submits ordinary text
- **THEN** the interface displays the user message, the local runtime state, and either the generated local response or a clear local runtime failure

### Requirement: Shared interactive command dispatch
The application SHALL support `/doctor` and `/quit` in the Textual interface. `/doctor` SHALL run the existing no-input diagnostic operation and render its outcome in the session; `/quit` SHALL exit cleanly without starting new inference or desktop control.

#### Scenario: Run diagnostics from an interactive frontend
- **WHEN** a developer enters `/doctor`
- **THEN** the interface displays the diagnostic outcome and preserves the session for further input

#### Scenario: Exit from an interactive frontend
- **WHEN** a developer enters `/quit`
- **THEN** the interface exits cleanly without starting new model inference or desktop control

#### Scenario: Unsupported slash command
- **WHEN** a developer enters an unsupported slash command
- **THEN** the interface reports that the command is unsupported and remains available for input

### Requirement: Restricted startup surface
The application SHALL expose only `max-agent` and `max-agent --chat` as supported public startup forms. It MUST NOT expose `doctor`, `download-model`, `validate-model`, `benchmark`, `--doctor`, `--fallback`, or `--textual` as public command-line operations. Removing those public operations MUST NOT require deletion of their underlying local model-management or benchmark implementation modules.

#### Scenario: Unsupported legacy CLI operation
- **WHEN** a developer invokes a removed command or option
- **THEN** the command exits with usage feedback and does not start a different frontend or trigger model, desktop, or download work
