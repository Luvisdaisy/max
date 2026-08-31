## Why

真实 baseline 已能稳定写入单一 JSON，但 CLI 会在测试结束后无条件生成报告，并因 Matplotlib 默认字体缺少中文字形而
向终端输出大量警告。现有报告还只比较成功率和耗时，缺少可复算的任务总分、完整模型指标表和一致的多模型可视化。

## What Changes

- **BREAKING** `max --baseline` 完成后只写运行 JSON，不再自动生成任何报告；报告仅由显式
  `max --baseline -report <json...>` 触发。
- 每题执行结束后按版本化的 0–100 分公式计算效果与效率总分，将总分、分项和算法版本写入同一运行 JSON；完整批次
  同时保存所有可测任务的平均总分和覆盖率。
- 将显式报告改为一个 `report.md` 加相对引用的 `charts/*.png`：表格每次运行一行，行名仅为模型名，列包含总分、
  成功率、步长、运行时间、工具调用/失败和执行 Token 等参数，不包含评审 Token。
- 为总分、成功率、平均步长、平均执行/总时长、工具调用、工具失败和执行 Token 分别生成多模型柱状图；同一模型在
  所有图中固定使用同一种颜色。
- 图表生成前显式选择已安装的中文字体；找不到可用字体时给出清晰错误并停止，不再生成缺字图片或刷出 Glyph 警告。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `baseline-evaluation-evidence-reporting`: 将自动报告改为显式多模型 Markdown 报告，并为单题与批次增加版本化总分。

## Impact

- 影响 `src/max_gui/baseline/models.py`、`service.py`、`report.py`、`comparison.py`、`src/max_gui/cli.py`、baseline
  测试与中文使用文档。
- 不增加前端或服务端技术栈，继续使用 Python 与现有 Matplotlib；报告目录只保留 Markdown 和其引用的 PNG 图表。
- 本变更应在 `fix-baseline-evaluation-evidence-reporting` 归档后应用和归档，使其能够修改正式的
  `baseline-evaluation-evidence-reporting` capability，且不会与旧自动报告契约并存。
