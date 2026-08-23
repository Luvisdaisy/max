## Why

当前每次 `think` 都把同一会话的全部消息编码进模型请求；虽然仅内联最近一张图片，旧用户指令、助手正文和工具结果仍会随会话增长反复消耗上下文。GUI 操作的判断主要依赖当前任务、最新画面和刚发生的动作，因而需要把审计用全量历史与推理用最小上下文明确分离。

## What Changes

- 为每个新用户任务建立独立的推理上下文胶囊：包含当前用户指令、最新可用截图、任务状态与受限的近期动作历史，而不是重放整个会话。
- 保持同一任务内 OpenAI 工具调用与工具结果的协议配对；在该任务完成、失败或被明确替换后，后续新任务不再默认携带旧任务的完整消息。
- 为“继续／重试”等延续性输入保留可恢复的任务目标、当前子任务、上一步动作和核验结论；对指代不明确且无法从最新画面确定目标的情况要求模型先澄清或重新观察。
- 全量会话消息、截图引用、检查点和运行事件继续本地持久化，用于 TUI 回放、中断恢复与审计；它们不再等同于默认模型上下文。
- 在模型调用诊断中记录实际发送的任务上下文规模与裁剪情况，以验证 token 节省，不记录截图字节、用户敏感输入或完整模型正文副本。

## Capabilities

### New Capabilities

- `task-context-capsule`：构建、裁剪与恢复单个 GUI 任务所需的最小推理上下文。

### Modified Capabilities

- `multimodal-inference`：只编码调用方选定的任务上下文和其中最新有效截图。
- `react-agent`：在任务边界创建或续接上下文胶囊，并保证任务内工具调用链完整。
- `session-store`：持久化任务级恢复语义，同时保留与推理上下文分离的全量会话历史。
- `run-observability`：记录上下文裁剪和已知 token 用量的诊断汇总。

## Impact

- `src/max_gui/agent/graph.py`、`state.py`：任务边界、任务状态和每次 think 的消息选择。
- `src/max_gui/inference/client.py`：任务上下文消息编码与图像选择入口。
- `src/max_gui/session/store.py`、`src/max_gui/observability/`：任务元数据与安全的裁剪诊断。
- 测试：`tests/test_agent.py`、`tests/test_inference.py`、`tests/test_session_store.py` 以及运行事件覆盖。
