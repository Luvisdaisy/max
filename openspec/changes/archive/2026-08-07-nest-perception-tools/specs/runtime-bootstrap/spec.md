## MODIFIED Requirements

### Requirement: Explicit controlled desktop probe
The system SHALL perform screenshot, OCR, and desktop-input minimal examples only through an explicit Doctor desktop-probe option. The probe MUST use a temporary controlled test window and MUST confirm that the intended target is the Windows foreground window before input. When invoked explicitly, the probe MUST make a bounded request for its own temporary window to become foreground before that confirmation. It MUST discard captured images unless explicitly requested for ignored artifacts, and report unsupported non-interactive sessions as skipped or failed without sending input to another application. A skipped foreground check MUST state that no desktop input test was executed and how to rerun it in an interactive Windows session.

#### Scenario: Explicit probe completes in a controlled session
- **WHEN** a developer invokes Doctor with the desktop-probe option in an interactive authorized Windows session
- **THEN** Doctor verifies an in-memory screenshot, OCR against a non-sensitive test image, and the temporary window's controlled click and text-input result, then archives the outcome

#### Scenario: Foreground focus is unavailable
- **WHEN** the explicit desktop probe cannot make its temporary controlled window the Windows foreground window
- **THEN** Doctor reports the desktop probe as skipped, states that no mouse or keyboard input was emitted, explains that the interactive session must be brought to the foreground before rerunning it, and exits according to the remaining checks

#### Scenario: Default Doctor execution
- **WHEN** a developer runs Doctor without the desktop-probe option
- **THEN** Doctor performs only no-input runtime and base-tool readiness checks and identifies the desktop probe as skipped with instructions for explicit execution
