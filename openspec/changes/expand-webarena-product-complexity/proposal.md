## Why

现有 WebArena 已具备多页面协作网站的基本骨架，但页面数据、实体关系和反馈状态仍偏静态，许多复杂任务
只能依赖固定字段组合来模拟工作流。这会限制它对 Agent 的信息检索、上下文保持、状态依赖、异常恢复与
结果核验能力的区分度。

现在需要在保持纯本地、可重置、可审计边界不变的前提下，将评测场完善为更接近真实团队协作产品的可见
工作流，并让新增复杂度可以被任务集和独立评分可靠使用。

## What Changes

- 扩展项目、任务、成员和活动记录之间的可见关系，提供项目详情、任务筛选视图、活动时间线与可追踪的
  业务上下文。
- 为任务增加状态流转、负责人负载、截止日期、标签、子任务与评论草稿等本地业务字段，并提供可见的
  创建、编辑、筛选、批量更新、确认和撤销反馈。
- 丰富工作台、项目、任务、日历和报表视图，使 Agent 必须读取跨页信息并基于可见事实完成多步骤操作，
  而不是只完成独立表单填写。
- 增加加载、空状态、表单校验、保存成功、撤销窗口和冲突提示等确定性 UI 状态，形成可评测的恢复与
  验证路径。
- 扩展本地业务 API、重置状态和任务 schema，使实体变化、跨页依赖和关键反馈可以被后端独立评分；不向
  Agent 暴露任务答案或评分接口。
- 更新一批 WebArena 任务及覆盖校验，降低同构换名任务占比，并为新增流程提供固定的冒烟覆盖。
- 将工具预算与禁止动作改为执行期护栏，并为每题隔离浏览器 profile、固定运行条件与环境失败分类，
  使评测结果具备可复现的执行边界。
- 修订逐题与汇总报告，保留未知指标语义，并按难度、能力和任务族呈现可解释的结果分布与运行配置。

## Capabilities

### New Capabilities

- `webarena-collaboration-workflows`：本地协作实体、跨页工作流、确定性反馈和可评分业务状态。
- `webarena-product-experience`：面向 Agent 的高信息密度页面、详情层级、空/错/成功状态和可访问交互。

### Modified Capabilities

- `web-gui-benchmark`：扩展可见业务交互、每题可重置状态与后端独立评分所覆盖的实体和反馈。
- `difficulty-layered-benchmark-tasks`：调整任务覆盖规则，使复杂任务包含真实的信息依赖、状态流转或恢复路径。
- `vue-vite-benchmark-arena`：扩展统一协作网站的业务页面和可点击站内工作流。
- `agent-task-evaluation`：将工具限制、浏览器运行条件、环境错误隔离和报告口径改为执行期可验证契约。

## Impact

- 影响 `src/max_gui/benchmark/web.py`、`src/max_gui/benchmark/tasks.py`、
  `artifacts/benchmarks/web-gui-v2.json`、`tests/test_benchmark.py` 与
  `docs/web-gui-benchmark.md`。
- 影响 `frontend/benchmark-arena/src/main.js`、`style.css` 与构建产物；继续由单个回环 FastAPI
  进程托管，不增加运行时外部服务。
- 保持 `max-gui --benchmark`、10/100 条选择、截图加键鼠操作、评分接口隔离和现有任务报告入口不变。
