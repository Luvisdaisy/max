## Context

现有仓库拥有 Pydantic、LangChain、LangGraph 和只读感知工具注册表，但没有任务状态或状态图。技术设计已规定编排器是唯一推进任务状态的组件，并禁止工具之间串联高风险副作用。详见 `proposal.md` 和 `specs/agent-orchestration/spec.md`。

## Goals / Non-Goals

**Goals:**

- 建立可直接以 mock 工具运行的单任务 LangGraph 图，并使状态和结果可序列化。
- 用最小 LangChain 提示词构造层向未来规划工具提供目标、观察、历史和推理模式；提示词本身不调用模型。
- 将恢复、预算、中止和人工等待编码为显式边与终态，确保没有自由循环。

**Non-Goals:**

- 不实现 `invoke_model`、`approve_action`、`execute_action`、`verify_result`、`recover` 或归档工具的真实业务逻辑。
- 不将状态机接入公共 CLI，不加载模型，不保存截图，也不启用任何桌面输入。
- 不实现多任务并发、持久化检查点、网络 Provider 或 LangGraph 自由式 Agent Executor。

## Decisions

### TypedDict 运行时状态与 Pydantic 外部结果

LangGraph 图使用 `TypedDict` 描述可归并的运行时状态，入口/终态 API 使用 Pydantic 模型验证任务请求与结果。选择该组合而非让 Pydantic 模型直接作为图状态，以匹配 LangGraph 的局部状态更新语义，同时维持调用边界的严格校验。

### 节点只调用注册表

每个节点根据固定工具名称构造最小 payload 并调用现有 `ToolRegistry`；回执被归一化成无图像、无输入明文的摘要后写入状态。选择注入注册表和工具名称映射而非直接导入实现，使 mock、替换和后续插件扩展不改变图结构。

### 显式条件边而非 Agent Executor

状态图固定为 `observe → plan → guard → act → verify`，并通过条件边转入 `recover`、`waiting_user`、`failed` 或 `succeeded`。恢复计数和最大步数由条件函数检查。选择显式图而非 Agent Executor，确保任何执行工具都必须先经过审批节点，且每一条终止路径可测试。

### 规划提示词只产生结构化上下文

使用 `ChatPromptTemplate` 生成包含目标、当前观察摘要、最近步骤和 `fast`/`deliberate` 模式的消息。实际模型调用留给后续 `invoke_model` 工具；这样当前变更可以验证提示词与状态机而不加载本地权重。

## Risks / Trade-offs

- [依赖工具尚未实现] → 通过注入 mock 工具验证图；运行时缺失工具立即转为失败，不伪造行为。
- [状态字典包含敏感或大型对象] → 仅保存回执摘要、状态指纹、哈希和长度，拒绝写入图像对象及文本输入明文。
- [恢复边导致循环] → 对恢复与审慎规划分别设置上限，第三次无进展只进入人工等待。
- [LangGraph 状态更新不一致] → 以单元测试覆盖每条条件边和不可变终态，节点只返回局部更新。

## Migration Plan

1. 添加状态/结果契约、提示词构造和图装配模块。
2. 实现注册表适配节点与所有条件边，并以 mock 工具覆盖成功、失败、恢复、等待和中止。
3. 将技术设计报告的编排器从后续设计移至受限的当前实现基线。
4. 运行完整单元测试、Ruff、`pip check` 与不启用桌面控制的编排器示例。
5. 回退时移除 CLI/调用方对图装配的引用；本变更不迁移数据或修改桌面工具权限。
