## ADDED Requirements

### Requirement: Structured Prompt Engineering for Task Accuracy
The GUI Agent SHALL use enhanced prompt engineering to improve task execution accuracy.

#### Scenario: Structured Output Compliance
- **WHEN** model receives task
- **THEN** model SHALL output in strict JSON format with `thought`, `subtask`, `plan`, `tool_calls`, `status`, and `reason`

### Requirement: Success/Failure Detection
The GUI Agent SHALL include explicit success/failure determination after each tool call.

#### Scenario: Post-Tool Verification
- **WHEN** tool call executed
- **THEN** model SHALL analyze new screenshot and explicitly state success/failure with reason

### Requirement: Plan Management
The GUI Agent SHALL maintain numbered subtask plans and support plan updates.

#### Scenario: Plan Update
- **WHEN** current plan fails
- **THEN** model SHALL output "改计划" and provide new numbered plan

### Requirement: Iteration Management
The GUI Agent SHALL support multiple iterations with clear task completion marking.

#### Scenario: Subtask Completion
- **WHEN** current subtask finished
- **THEN** model SHALL output "子任务完成" or "下一子任务"
