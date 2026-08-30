## 1. 工具门面与结果契约

- [x] 1.1 盘点默认注册表的工具意图、快照上下文和后端可用性，定义语义优先及视觉后备的最小允许集合
- [x] 1.2 扩展 `ToolResult` 的脱敏执行事实 data，并确保工具实现不直接写入 Agent 任务状态
- [x] 1.3 调整语义工具 schema 与描述，使元素引用、适用条件和禁止用法机器可校验且不暴露后端细节
- [x] 1.4 在 `ToolRegistry`／Agent 阶段门禁中实现按主 UI 上下文选择语义工具及视觉后备，保留当前帧、移鼠和单次副作用规则

## 2. Policy 提示词与状态上下文

- [x] 2.1 重写固定中文 Policy system，覆盖单步决策、语义／模态优先、当前元素约束、失败恢复和严格完成条件
- [x] 2.2 将任务状态渲染为 TASK、CURRENT SUBGOAL、PROGRESS、ENVIRONMENT、VISIBLE UI、WORKING MEMORY、RECENT ACTIONS、LAST RESULT 八段，并实施脱敏、排序和大小上限
- [x] 2.3 为副作用语义工具 schema 增加短 intent 与受限 expectation 元数据，并在分派前从后端参数中剥离
- [x] 2.4 接入 intent 动作摘要、expectation 后置验证、未验证恢复提示及既有 `task_complete` 独立完成核验

## 3. 测试与说明

- [x] 3.1 为 ToolResult data、后端隐藏、快照优先、视觉后备和阶段二次门禁补充单元测试
- [x] 3.2 为 Policy 上下文八段、模态优先、元素相关性排序、失败不原样重试和不持久化 system 补充 Agent 测试
- [x] 3.3 用 fake browser、fake AX 和 fake desktop 覆盖跨通道语义动作、预期推进、完成证据与坐标后备集成流程
- [x] 3.4 在真实 macOS 与受控浏览器各执行一次小型冒烟，单独记录已验证能力、权限／服务前提和未验证边界
- [x] 3.5 更新 README 既定章节中工具表面、Policy 决策、观察验证和后备边界说明
- [x] 3.6 运行 `uv run ruff format src tests`、`uv run ruff check src tests`、相关 pytest、完整 pytest 与 `openspec validate unify-semantic-tools-and-policy-context --strict`
