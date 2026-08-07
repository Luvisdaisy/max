## MODIFIED Requirements

### Requirement: Default chat-first terminal interface
The application SHALL provide a CLI-first terminal interface as its default interactive experience, with command input, visible status feedback, command history, and a graceful exit action. The default interface SHALL use the Typer/Rich/Prompt Toolkit interaction path; Textual SHALL NOT be required to start the default interface.

#### Scenario: Start the default interface
- **WHEN** a developer starts `max-agent` with no operation argument in an interactive terminal
- **THEN** the application opens the CLI-first interactive interface and accepts either chat text or slash commands without requiring Textual

#### Scenario: Send chat text before an AI backend exists
- **WHEN** a developer submits ordinary chat text while no AI backend is configured
- **THEN** the interface appends a clear local message that the AI backend is not configured and does not fabricate a model response

#### Scenario: Start the explicit chat interface
- **WHEN** a developer runs `max-agent --chat`
- **THEN** the application starts the same CLI-first interactive interface used by the default entry point

### Requirement: Terminal compatibility fallback
The application SHALL provide a line-oriented interactive console as the primary development interaction path, with command history and the shared command set. Textual MAY be provided as an optional advanced interface, but its availability or initialization SHALL NOT be required for the primary CLI interaction path.

#### Scenario: Run the primary interactive console
- **WHEN** a developer starts the application in a terminal that supports the CLI interaction path
- **THEN** the application provides line input, command history, Rich-rendered feedback, and `/doctor` and `/quit` handling

#### Scenario: Use the optional advanced UI
- **WHEN** a developer explicitly selects a Textual interface and the Textual dependency is available
- **THEN** the application may start the advanced UI while preserving the same operation-dispatch semantics as the CLI interaction path

#### Scenario: Textual is unavailable
- **WHEN** Textual is not installed or cannot initialize
- **THEN** the primary CLI interaction path remains usable and the application does not fail solely because the optional advanced UI is unavailable

### Requirement: Compatible one-line command access
The application SHALL provide non-interactive one-line access to the current diagnostic and chat entry points while preserving existing local development operations.

#### Scenario: Run diagnostics as a one-line command
- **WHEN** a developer runs `max-agent doctor` or the supported Doctor flag
- **THEN** the application writes the diagnostic result and exits with the diagnostic status code

#### Scenario: Start chat as a one-line command
- **WHEN** a developer runs `max-agent --chat`
- **THEN** the application starts the CLI-first interactive interface without starting model inference or desktop control
