## Why

当前评测首页只有一个固定执行 100 条任务的 Start 按钮。开发调试和模型冒烟验证需要一个更短、可复现的 10 条入口，同时仍要保留完整 100 条评测。

## What Changes

- 在评测首页提供清晰区分的「运行 10 条」与「运行 100 条」按钮，并显示所选批次的进度。
- 规定 10 条批次从版本化完整任务集按难度确定性分层选取，覆盖 easy、medium、hard，复用同一重置、执行、评分和报告链路。
- 在报告和运行状态中记录本次选择的任务数量，避免将小批次结果误认为全量评测结果。

## Capabilities

### New Capabilities

<!-- 无。 -->

### Modified Capabilities

- `web-gui-benchmark`: 评测首页可选择并展示 10 条或 100 条任务批次。
- `agent-task-evaluation`: 自动评测入口可接收受限的批次大小，并在结果中保留该实验范围。

## Impact

- 修改 `src/max_gui/benchmark/service.py` 与 `src/max_gui/benchmark/web.py` 的批次选择和状态展示。
- 为任务集选择、首页 POST 行为与报告元数据补充测试和中文文档。
- 不新增第三方依赖，不改变默认 TUI 启动路径，也不改变 100 条任务定义本身。
