## Context

当前 GUI Agent 提示词工程主要集中在 `src/max_gui/agent/prompts.py` 的 `GUI_SYSTEM_PROMPT` 和 `compose_gui_system_prompt` 函数，以及 `src/max_gui/agent/plan.py` 中的计划提取和推进逻辑。模型在执行桌面任务时准确率较低，主要问题是缺少结构化输出约束和明确的成功/失败判定机制。

## Goals / Non-Goals

**Goals:**
- 提升模型在 ReAct 流程中的执行准确率，特别是定位、点击和输入操作
- 强制模型严格遵守「必须截图核验 + 精确定位 + 不要只报文字」的契约
- 增强子任务计划管理能力（编号列表、改计划、子任务完成标记）

**Non-Goals:**
- 不在此变更中添加新工具或修改现有工具实现
- 不改变模型架构或 LangGraph 状态图
- 不涉及 UI 界面或 TUI 界面改动

## Decisions

- 使用结构化 JSON 输出强制（`thought`、`subtask`、`plan`、`tool_calls`、`status`、`reason`），让模型必须按固定格式回复
- 在 `GUI_SYSTEM_PROMPT` 末尾添加「成功/失败判定」和「改计划」机制
- 增强 `ingest_assistant_plan` 和 `advance_subtask_after_tools` 函数对结构化输出的支持
- 保留现有中文提示词风格，保持与用户可见文案的一致性

## Risks / Trade-offs

- [JSON 格式限制] → 模型可能偶尔生成非标准 JSON，但仍可通过正则或简单解析处理
- [提示词长度增加] → 模型上下文窗口压力小，影响可接受

## Migration Plan

- 修改提示词工程后，重新运行 Agent 测试
- 观察任务执行准确率提升情况

## Open Questions

- 结构化 JSON 输出的确切 schema 细节是否需要进一步细化？
