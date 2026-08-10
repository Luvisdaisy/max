## Why

仓库已有只读感知工具和工具注册入口，但没有能够维护任务状态、调用工具并依据结构化回执停止或恢复的核心。LangChain 和 LangGraph 已固定为项目依赖与技术路线，现在需要实现一个受限、可测试的编排器，以建立后续模型、审批和执行工具的唯一集成边界。

## What Changes

- 新增基于 LangGraph 的 `Agent Orchestrator`，以显式状态图推进初始化、观察、规划、审批、执行、验证、恢复和终态。
- 定义最小、可序列化的任务状态、步骤预算、工具回执记录、失败码和终止结果契约。
- 使用 LangChain `ChatPromptTemplate` 构造结构化规划提示词，但不在编排器内加载模型或直接调用桌面/视觉 SDK。
- 编排器仅经 `tools/registry.py` 调用工具；未知工具、失败回执、预算耗尽、用户取消和不可恢复错误进入可审计终态。
- 提供 mock 工具和状态机单元测试，覆盖成功、工具失败、无进展恢复、人工处理和中止路径。
- 更新技术设计报告的当前实现基线，明确首版只提供编排与 mock 验证，不启用真实桌面控制或模型推理。

## Capabilities

### New Capabilities

- `agent-orchestration`: 基于 LangGraph 的单任务状态机、结构化工具调用和受限恢复/终止行为。

### Modified Capabilities

无。

## Impact

- 新增 `src/max_agent/orchestration/` 与可能的共享状态/提示词模块，并扩展现有工具注册契约以满足编排调用。
- 新增状态机、提示词和工具回执驱动的测试；不新增依赖、不改动真实桌面执行能力。
- 更新 `tech-design.md` 的已实现边界和验证命令说明。
