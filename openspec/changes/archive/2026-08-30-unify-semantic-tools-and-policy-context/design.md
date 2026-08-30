## Context

当前 runtime 已在同一 Python 进程中拥有 `ToolRegistry`、`Tool`／`ToolResult`、BrowserBackend、MacOSAXBackend、视觉桌面后备、`UISnapshot` 和 `TaskContext`。但 `build_default_registry()` 同时注册底层键鼠、OCR、图像与语义工具，`_allowed_tool_names()` 只按截图和 UI 快照作粗粒度筛选；`GUI_SYSTEM_PROMPT` 也以鼠标坐标闭环为主。已有状态层已经提供 UI 快照、进度和 expectation，适合作为 Policy 的动态信息源。

本设计延续现有 `think → act → observe` 图和严格后置观察，不改变 provider 的原生 tool calling。目标是收敛模型的决策表面，而不是重建执行架构。

## Goals / Non-Goals

**Goals:**

- 让 Agent loop 只通过 `ToolRegistry.schemas()` 和 `ToolRegistry.invoke()` 使用统一工具，不认识 Playwright、AX、CGEvent、selector 或 locator。
- 在有可信 `UISnapshot` 时优先给模型一组小而一致的语义动作；在无快照或快照无法覆盖目标时提供受原有门禁保护的视觉后备。
- 将每轮输入整理成稳定、紧凑且可测试的 Policy 上下文，要求模型恰好选择一个下一步，并为副作用记录短 intent 与受限 expectation。
- 保持工具执行、状态更新和业务成功三者分离：工具返回执行结果，观察验证预期，完成声明验证用户目标。

**Non-Goals:**

- 不引入 MCP、RPC、插件发现、独立工具服务、多进程沙箱、事件总线或多 Agent 编排。
- 不删除现有鼠标坐标安全闭环，也不让 AX／Playwright 细节、坐标或 locator 出现在语义工具 schema。
- 不把复杂多步流程包装为新的 Skill，不要求模型输出思维链，不持久化文本输入或截图正文。
- 不改变现有原生 tool calling 协议为 JSON 正文协议。

## Decisions

### 1. 一个 Registry、两类模型暴露面

保留单个 `ToolRegistry` 作为唯一注册与调用入口。工具实现按内部职责保持在 `semantic.py`、`desktop.py`、`ocr.py` 等模块，不新增 resolver 服务。`_allowed_tool_names()` 基于当前有效 `UISnapshot` 返回一个语义优先集合；浏览器或原生快照可操作时，隐藏同一意图的低层坐标工具。快照缺失、元素不可用或明确视觉定位场景时，才暴露截图、OCR 与既有鼠标后备。

备选方案是让模型同时选择 browser／AX／坐标 backend；它会把后端差异变成推理负担。另一方案是立刻删除视觉工具；它会失去 AX／DOM 覆盖不到的真实桌面回退能力，故拒绝。

### 2. 语义 ToolResult 只报告执行事实

扩展 `ToolResult` 为稳定、脱敏的结果契约：`ok`、`code`、短文本与可选结构化 `data`，其中 `data` 仅包含动作类型、有效元素引用或通道等非敏感执行事实。工具不得写 `progress`、`current_subtask`、长期事实或 `completion_verified`。`act` 写入动作摘要，`observe` 用前后快照验证 expectation 并推进进度。

备选方案是由工具直接改 AgentState；这会绕过后置观察，使“调用成功”被误当作“用户任务成功”。

### 3. 固定 Policy 契约加动态八段上下文

固定 system 仅包含角色、恰好一步、语义优先、模态优先、仅使用当前 UI 元素、失败不原样重试、严格完成条件和视觉后备安全边界。每轮由 `task_context_message()` 或其拆分渲染器输出：TASK、CURRENT SUBGOAL、PROGRESS、ENVIRONMENT、VISIBLE UI、WORKING MEMORY、RECENT ACTIONS、LAST RESULT。它不显示 locator、坐标、完整 OCR、键入内容或历史可执行编号。

模型仍以原生 function call 选择动作。对副作用调用，schema 接受可选 `intent`（短、无 reasoning）和既有受限 `expectation`；系统从参数剥离这些元数据再传给执行实现，防止实现 schema 被污染。纯观察与 `task_complete` 不要求 intent。

备选方案是要求正文 JSON 的 `intent/action/expectation`；这会与已有原生 tool calling 冲突，并增加解析失败面，故拒绝。

### 4. 统一模式下的验证与恢复

所有成功副作用，无论由 browser、AX 或视觉后备执行，均进入同一个 `observe`。意图仅用于日志和相同失败调用检测；expectation 仍使用现有有限枚举验证。工具失败、预期未满足或 UI 版本过期时，下轮上下文把原因写为 LAST RESULT，且禁止立即提交相同工具和相同目标参数；重新观察、目标变化或策略变化后方可重试。`task_complete` 继续仅在当前可见完成证据及独立核验通过时结束。

### 5. 渐进迁移，不做运行时拆分

先把 schema 分组和上下文渲染接入现有 runtime，再调整提示词、动作元数据与结果结构，最后补回归测试。现有工具名和内部后端协议尽量维持，以降低 benchmark、fake backend 和测试夹具的迁移风险；只有模型可见的低层工具暴露策略改变。

## Risks / Trade-offs

- [语义快照不完整导致无动作可选] → 保留截图／OCR／视觉后备，并在上下文中清楚标记快照缺失或过期。
- [隐藏低层工具破坏既有坐标任务] → 按 UI 快照和操作类型渐进筛选；为浏览器、原生弹窗与 vision 路径分别覆盖测试。
- [额外上下文增加 token] → 固定上限，按模态、当前子目标、焦点和近期变化排序元素，仅渲染与决策有关的字段。
- [intent 被当作 reasoning 或泄露] → 限制长度、禁止持久化推理原文，仅记录短摘要与脱敏参数。
- [工具结果 data 被误当作业务证据] → 文档与测试明确它仅代表执行事实，完成仍需后置观察和完成声明。

## Migration Plan

1. 增加语义工具表面和 ToolResult 数据契约的单元测试，不改变执行后端。
2. 接入按快照／模态选择的 schema 集合与视觉后备，保留阶段二次门禁。
3. 引入 Policy system 与八段上下文渲染，衔接 intent、expectation、进度及恢复摘要。
4. 用 fake browser、fake AX 和 fake desktop 跑跨通道、失败恢复和完成校验集成测试；再进行真实 macOS 只读／受控浏览器冒烟并单独记录结果。
5. 回滚时恢复原 schema 暴露及旧 system 文案；Registry、后端和会话数据保持可读。

## Open Questions

- 首版是否将 `set_file_input` 直接命名为 `upload_file`，还是为兼容现有 browser backend 保留旧名称并仅改善描述？建议先保留名称，待真实文件选择器覆盖后再做破坏性重命名。
- 文件搜索是否纳入本变更？当前项目没有安全、跨目录的 `find_file` 工具，建议保持不新增，避免扩大文件系统权限范围。
