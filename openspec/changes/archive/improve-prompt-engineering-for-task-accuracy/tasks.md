## 1. Update System Prompt

- [x] 1.1 Update `GUI_SYSTEM_PROMPT` in `src/max_gui/agent/prompts.py` to enforce structured JSON output
- [x] 1.2 Add success/failure detection and "改计划" mechanism

## 2. Enhance Plan Management

- [x] 2.1 Update `ingest_assistant_plan` and `advance_subtask_after_tools` in `src/max_gui/agent/plan.py`
- [x] 2.2 Ensure plan updates are properly handled

## 3. Verification

- [ ] 3.1 Run existing tests
- [ ] 3.2 Test prompt engineering changes with sample GUI tasks
