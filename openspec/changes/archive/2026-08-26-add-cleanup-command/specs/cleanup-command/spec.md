## ADDED Requirements

### Requirement: Cleanup command targets only local records

`max-gui cleanup` MUST target only the project record directories `artifacts/screenshots/`, `artifacts/runs/` and `artifacts/sessions/`. It MUST NOT delete the directories themselves or any path outside those directories.

#### Scenario: Cleanup removes all record contents

- **WHEN** the three record directories contain files and nested directories
- **THEN** the command removes their contents and leaves all three directories present and empty

#### Scenario: Missing record directory

- **WHEN** one or more record directories do not exist
- **THEN** the command creates or leaves each target directory present and reports zero removed records for the missing directory

### Requirement: Cleanup executes without interaction

The command MUST delete the targeted record contents directly without reading standard input or asking for confirmation. The command MUST NOT accept confirmation or compatibility parameters such as `--yes`.

#### Scenario: Direct cleanup

- **WHEN** the user runs `max-gui cleanup`
- **THEN** the command deletes the targeted record contents without interaction and reports the result

#### Scenario: Confirmation parameter is rejected

- **WHEN** the user runs `max-gui cleanup --yes`
- **THEN** argument parsing rejects the unsupported parameter and does not delete records

### Requirement: Cleanup reports failures

The command MUST report each failed target or entry and MUST exit with a non-zero status if any deletion fails. It MUST attempt the remaining target directories after an individual failure.

#### Scenario: One target cannot be removed

- **WHEN** deletion of one target entry raises an operating-system error
- **THEN** the command reports that failure, attempts the other targets, and exits with status 1
