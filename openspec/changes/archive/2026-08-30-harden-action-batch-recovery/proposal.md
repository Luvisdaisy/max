## Why

默认 Agent 已停用 `locate`，但运行期仍有遗留的模型可见提示、恢复提示和坐标错误文案提及 `locate` 或 `target_id`。它们会把模型重新引向不可用的调用路径。

另外，单次模型回复包含多个桌面副作用时，`act` 会正确阻断后续调用并返回 `action_batch_blocked`，但恢复护栏没有识别该错误。模型重复提交批次时只能耗尽迭代上限，无法得到明确且有界的失败结果。

## What Changes

- 清理默认 Agent 可见的 `locate` / `target_id` 遗留提示、恢复提示与坐标错误文案；历史定位事实不再回注模型上下文。
- 将 `action_batch_blocked` 作为批次级恢复失败：每个被阻断的回复只计一次，连续重复达到既有恢复阈值后以 `recovery_exhausted` 结束。
- 在恢复提示和阻断错误中明确要求下一次只提交一个副作用调用，并先读取该动作后的截图。
- 补充提示词、错误文案和恢复边界的自动化测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `react-agent`：默认模型上下文不再暴露已停用的定位编号；重复多副作用批次进入恢复护栏并有界终止。
- `grounded-short-term-memory`：历史 `locate` 事实仍可兼容读取，但不再作为模型决策事实输出。

## Impact

- 影响 `src/max_gui/agent/graph.py`、`src/max_gui/agent/context.py`、`src/max_gui/agent/prompts.py`、`src/max_gui/tools/desktop.py` 及其测试。
- 不删除 OmniParser、`locate` 实现、会话字段或 `mouse_move(target_id)` 的旧会话兼容分支。
