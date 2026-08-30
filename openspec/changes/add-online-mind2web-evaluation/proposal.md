## Why

现有本地 Web GUI 评测场使用仓库自定义任务、状态重置和隐藏断言，不能反映 Agent 在真实网站上的可迁移网页操作能力。已在 `artifacts/Online-Mind2Web/` 引入上游判分仓库，现在需要建立受控适配层，使现有截图与键鼠 Agent 能产出官方可复核的轨迹，而不把真实站点故障或高风险操作误记为模型失败。

## What Changes

- 新增 Online-Mind2Web 任务清单加载、显式安全筛选与运行前预检；不自动下载受限数据，也不自动接受数据集访问条款。
- 新增仅在用户显式启动时执行的专用真实网页评测流程：隔离浏览器配置、固定起始 URL、单题超时与可中断批次。
- 新增与 Online-Mind2Web v2 一致的逐题轨迹导出：动作、思考、页面 URL、截图和最终回答以单个步骤对象原子关联。
- 新增 WebJudge 调用与本地汇总，分别报告可执行性、模型任务结果、效率和安全阻断；WebJudge 仅在提供独立评测凭据后运行。
- 保留当前本地 benchmark，作为迁移期间的独立回归能力；本变更不删除现有 Vue 评测场，也不声称已完成真实任务评测。

## Capabilities

### New Capabilities

- `online-mind2web-task-selection`: 加载经用户授权取得的上游任务数据，以版本化安全清单选择可运行任务并明确预检结果。
- `online-mind2web-run-orchestration`: 在隔离浏览器中从任务指定起始网站运行现有 Agent，并安全地控制批次、中断和环境失败。
- `online-mind2web-trajectory-export`: 把真实桌面操作导出为官方 v2 的可验证任务轨迹，防止动作、截图、URL 与思考错位。
- `online-mind2web-webjudge-reporting`: 调用上游 WebJudge 并输出与环境失败分离的可审计评测汇总。

### Modified Capabilities

- 无。

## Impact

- 新增 `src/max_gui/mind2web/`、评测 CLI 入口、测试和中文使用文档；复用 `AgentRunner`、桌面工具、会话与运行观测。
- 评测结果写入独立的 `artifacts/evaluations/online-mind2web/`，不修改上游 `artifacts/Online-Mind2Web/` 克隆内容。
- 需要用户自行取得 Online-Mind2Web 任务数据，并在运行 WebJudge 时提供独立的 OpenAI 兼容评测凭据；不得将凭据、真实账户或个人数据写入仓库或报告。
