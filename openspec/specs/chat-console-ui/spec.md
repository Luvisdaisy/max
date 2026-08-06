# chat-console-ui Specification

## Purpose

Provide a chat-first local console that gives the future GUI Agent a consistent interactive entry point while preserving direct access to the existing development operations.

## Requirements

### Requirement: Default chat-first terminal interface
The application SHALL provide a chat-first terminal interface as its default interactive experience, with a conversation transcript, a command input area, visible status feedback, and a graceful exit action.

#### Scenario: Start the default interface
- **WHEN** a developer starts `max-agent` with no operation argument in an interactive terminal
- **THEN** the application opens the chat-first interface and accepts either chat text or slash commands

#### Scenario: Send chat text before an AI backend exists
- **WHEN** a developer submits ordinary chat text while no AI backend is configured
- **THEN** the interface appends a clear local message that the AI backend is not configured and does not fabricate a model response

### Requirement: Shared interactive command dispatch
The application SHALL support `/diagnose` and `/quit` in every interactive frontend and SHALL dispatch them through the same operation core used by non-interactive commands.

#### Scenario: Run diagnostics from an interactive frontend
- **WHEN** a developer enters `/diagnose`
- **THEN** the frontend displays the diagnostic outcome and preserves the session for further input

#### Scenario: Exit from an interactive frontend
- **WHEN** a developer enters `/quit`
- **THEN** the frontend exits cleanly without starting model inference or desktop control

#### Scenario: Unsupported slash command
- **WHEN** a developer enters an unsupported slash command
- **THEN** the frontend reports that the command is unsupported and remains available for input

### Requirement: Terminal compatibility fallback
The application SHALL provide a line-oriented interactive fallback when the full terminal interface cannot be used.

#### Scenario: Start the fallback console
- **WHEN** a developer explicitly selects the fallback console
- **THEN** the application provides command history and supports the same `/diagnose` and `/quit` commands

### Requirement: Compatible one-line command access
The application SHALL provide non-interactive one-line access to the current diagnostic and chat entry points while preserving the existing local development operations.

#### Scenario: Run diagnostics as a one-line command
- **WHEN** a developer runs `max-agent --diagnose`
- **THEN** the application writes the diagnostic result and exits with the diagnostic status code

#### Scenario: Start chat as a one-line command
- **WHEN** a developer runs `max-agent --chat`
- **THEN** the application starts the default chat-first terminal interface
