## Why

当前评测场以 FastAPI 拼接 HTML，并将 20 个任务模板机械复制为 100 条。页面交互和任务难度不足以稳定评估 GUI Agent 从单一操作到多步骤、状态依赖和异常恢复的能力。

## What Changes

- **BREAKING**：以 Vue + Vite 重建 Agent 可见的评测场页面，移除旧版 FastAPI 服务端 HTML 页面、旧版业务路由及其兼容层。
- 采用单进程部署：FastAPI 继续只监听回环地址，托管 Vite 构建产物，并保留仅供运行器使用的重置、状态、启动和进度接口。
- 以 100 条显式、独立且不可由复制展开的任务替换 `web-gui-v1`；任务按 easy、medium、hard 分层，覆盖单一操作、同页组合、跨页工作流、状态依赖和异常恢复。
- 将评测场扩展为具有工作台、收件箱、项目、任务、日历、自动化、团队、报表和设置的统一协作网站；所有任务从统一入口开始，Agent 必须点击站内导航进入目标页面，不得由运行器直接打开目标业务路由。
- 以主要可见操作数作为难度硬门槛：easy 为 1 至 3 步，medium 为 5 至 6 步，hard 为 7 步以上；同时使用跨页、状态依赖、检索、确认和错误恢复约束避免机械点击堆叠。
- 重写任务指令，使其成为可直接发送给 Agent 的自然中文委托；评分按最终业务实体、导航检查点和可见交互结果判断，不以最后一次动作代号替代功能正确性。
- 保留首页「运行 10 条」与「运行 100 条」入口；10 条是固定的难度分层冒烟集，100 条为完整任务集。
- 保留现有 CLI 入口 `max-gui --benchmark`；不得要求用户改用新的命令或子命令。
- 提供可见的中断入口；评测运行时按 Escape 可停止当前题并终止本批次，不丢弃已经完成的结果。
- 更新任务加载、状态模型、评分测试、评测文档和项目说明，删除不再使用的旧版评测场代码与依赖。

## Capabilities

### New Capabilities

- `vue-vite-benchmark-arena`: 由 Vue + Vite 构建、FastAPI 单进程托管的本地可见评测场。
- `difficulty-layered-benchmark-tasks`: 100 条独立任务及其难度分层、覆盖范围和冒烟批次选择规则。

### Modified Capabilities

- `web-gui-benchmark`: 将评测场的可见 UI、状态重置和交互覆盖要求迁移至 Vue + Vite，且不保留旧版页面。
- `agent-task-evaluation`: 将版本化任务定义与显式启动批次的要求改为 100 条非复制的分层任务集，并保持 10/100 条评测入口。

## Impact

- 涉及 `src/max_gui/benchmark/`、`artifacts/benchmarks/`、`scripts/eval_agent.py`、测试、README 与 Web 评测文档。
- 新增 Node.js、Vue 与 Vite 的前端构建依赖；Python 运行器、评分和报告继续由现有 FastAPI/Python 链路承担。
- 删除 `src/max_gui/benchmark/web.py` 中旧版 HTML 业务页面及 `web-gui-v1.json`，不迁移历史任务或提供旧路由兼容。
