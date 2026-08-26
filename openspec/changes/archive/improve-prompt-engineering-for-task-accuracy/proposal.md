## Why

当前 GUI Agent 模型在执行桌面任务（如定位、点击、输入）时准确率较低，主要问题是提示词工程未充分约束模型行为，导致模型容易忽略「必须截图核验 + 精确定位 + 不要只报文字」的核心 ReAct 流程。

模型常出现：
- 直接声称「已点击」而不实际操作
- 坐标不准确或超出视图范围
- 缺少失败重试机制
- 计划不编号、不更新

这些问题在 macOS 桌面环境中尤为明显，严重影响用户任务执行成功率。

## What Changes

- 在 `GUI_SYSTEM_PROMPT` 中添加结构化 JSON 输出强制 + 成功/失败判定标准
- 增强子任务计划管理（编号列表、改计划、子任务完成标记）
- 增加迭代执行/失败重试机制的提示词约束
- 更新 `agent/plan.py` 以更好支持结构化输出和计划推进

## Capabilities

### New Capabilities
- prompt-engineering: 结构化提示词与严格行为约束，提升模型任务执行准确率

### Modified Capabilities
- react-agent: 强化 ReAct 流程中的执行核验和计划管理

## Impact

- 修改 `src/max_gui/agent/prompts.py`
- 修改 `src/max_gui/agent/plan.py`
- 修改 `src/max_gui/agent/graph.py`（可选）
- 更新测试（可选）
