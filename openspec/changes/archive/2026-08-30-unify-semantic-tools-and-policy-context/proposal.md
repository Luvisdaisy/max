## Why

当前 Agent 虽然已有注册表、浏览器／macOS 语义后端、结构化 UI 快照和动作预期，但默认模型工具集仍混合了语义动作、视觉坐标动作及实现导向命名；提示词也主要强调鼠标闭环，未把“当前子目标、已验证进度、可用 UI、上次结果、单步预期”组织成稳定的决策契约。这会增加小模型选择工具、避免重复失败和跨浏览器／原生弹窗切换时的负担。

本变更将现有能力收敛为轻量的统一语义工具门面和结构化 Policy 上下文，使 Agent loop 只依赖 `ToolRegistry` 与 `ToolResult`，而不暴露 Playwright、AX 或坐标执行细节；同时保持单进程 MVP，不引入 MCP、RPC、插件发现或多 Agent 框架。

## What Changes

- 为默认 Agent 定义按观察阶段暴露的精简语义工具集：元素操作、键盘、滚动、应用激活、浏览器导航、等待和严格完成声明；后端／locator／AX 引用仅保留在工具实现内部。
- 将视觉坐标工具与语义工具明确分层：有有效结构化 UI 快照时优先仅向模型暴露语义工具；无可靠语义目标时保留受既有截图、移鼠、后置观察门禁保护的视觉后备。
- 扩展统一 `ToolResult` 的机器可读动作结果摘要，使工具只报告执行结果，任务进度、工作记忆及完成判断仍由 Agent 的观察与验证链更新。
- 将固定系统契约改为“基于当前状态选择恰好一个下一步”的 Policy 契约，并将动态上下文渲染为任务、当前子目标、已验证／待验证进度、环境、可见 UI、工作记忆、近期动作与上次结果。
- 为副作用动作统一 `intent` 与受限 `expectation` 记录；`intent` 用于日志与重复检测，不要求模型输出思维链；只有后置观察满足 expectation 才推进进度，`task_complete` 仍需独立的完成证据。
- 为工具 schema、上下文裁剪、模态优先、失败恢复、严格 `done` 与浏览器／原生通道切换补充契约测试与文档。

## Capabilities

### New Capabilities

- `semantic-policy-toolset`: 面向模型的轻量语义工具门面、视觉后备边界及工具结果契约。
- `policy-decision-context`: 单步 Policy 固定契约、动态状态上下文、短 intent 与 expectation 的渲染及恢复规则。

### Modified Capabilities

- `agent-tools`: 默认工具暴露、ToolResult 结果边界与语义／视觉后备选择规则变更。
- `react-agent`: 每轮模型决策上下文、单步工具调用、预期验证和完成条件的行为变更。
- `semantic-ui-actions`: 当前 UI 快照中语义工具的选择与后置观察行为变更。

## Impact

主要影响 `src/max_gui/tools/protocol.py`、`registry.py`、`semantic.py`、`desktop.py`、`src/max_gui/agent/prompts.py`、`context.py`、`graph.py` 及其测试；更新 `README.md` 的既定相关章节。不会新增依赖、服务、进程间通信或持久化敏感输入，也不会移除当前坐标安全与独立完成核验链路。
