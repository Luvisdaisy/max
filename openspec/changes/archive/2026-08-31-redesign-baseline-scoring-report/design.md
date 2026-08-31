## Context

`max --baseline` 当前在 `run_baseline()` 写入时间戳 JSON 后由 CLI 无条件调用 `write_run_report()`，因此一次真实评测会
额外生成 HTML、Markdown、源 JSON 和 PNG。2026-08-31 的真实运行还证明，Matplotlib 默认 DejaVu Sans 无中文字形，
每次 `tight_layout()` 与 `savefig()` 都会输出大量 `Glyph missing` 警告。

现有结果已经包含逐题 success、执行/总耗时、actions、tool_calls、tool_failures 和执行 Token，足以在不引入新采集链路的
前提下计算稳定总分。报告输入仍限制为 1–5 份运行 JSON；用户确认表格每次运行一行，行名只使用模型名，且不展示评审
Token。

## Goals / Non-Goals

**Goals:**

- baseline 执行仅写一个运行 JSON，不自动生成报告或触发 Matplotlib。
- 每题写入可复算的 0–100 总分、分项、算法版本和评分完整性；完整批次写入平均总分与覆盖率。
- 显式报告只生成一个 Markdown 文档和相对引用的 PNG 柱状图，并按模型比较所有确认指标。
- 在 macOS、Windows 和常见 Linux 环境选择可用中文字体；不能正确渲染时明确失败。

**Non-Goals:**

- 不改变独立截图评审的成功公式、180 秒执行超时、工具安全护栏或 baseline 任务内容。
- 不用当前对比集合的最小值/最大值动态归一化，也不让报告生成过程重新调用模型。
- 不生成 HTML、额外汇总 JSON、内嵌 base64 图片或自动打开报告。
- 不在表格和图表中展示评审 Token。

## Decisions

### 1. 使用绝对参考值的版本化 100 分算法

新增纯函数以任务契约和单题结果计算 `baseline-score-v1`。安全违规直接得到 0 分；环境/用户确认阻断不评价模型，得到
`null`。其余任务按以下分项相加：

- 任务效果 70 分：评审 `pass=70`、`indeterminate=35`、`fail/review_error/no screenshot=0`。
- 执行时间 10 分：`10 × clamp(1 - execution_duration_ms / timeout_ms, 0, 1)`；当前 timeout 为 180 秒。
- 动作步长 5 分：`5 × clamp(1 - actions / 10, 0, 1)`。
- 工具调用 5 分：`5 × clamp(1 - tool_calls / 15, 0, 1)`。
- 工具可靠性 5 分：`5 × (1 - tool_failures / max(tool_calls, 1))`。
- 执行 Token 5 分：`5 × clamp(1 - execution_tokens / 100000, 0, 1)`。

总分四舍五入到两位。任一评分必需数值未知时，对应分项和总分均为 `null`，不得把未知值当零或重分配权重；记录
`complete=false` 和缺失字段。完整批次的 `overall_score` 是所有可测题总分的算术平均；存在未测或无分题时为 `null`，
同时记录 `score_coverage`。这比对当前候选模型做 min-max 更稳定，因为 JSON 写入时无需知道未来比较对象。

替代方案是只按成功率评分；不采用，因为无法区分同样完成任务但耗时、步长和资源成本显著不同的模型。动态相对评分也
不采用，因为加入或移除一份报告输入会改变历史模型分数。

### 2. 在运行 JSON 内保存总分、分项和算法元数据

单题记录增加 `score` 对象，包含 `version`、`total`、六个分项、`complete`、`missing_metrics` 和固定参考值。summary
增加 `overall_score`、`score_coverage` 与 `score_version`。评分在单题结束、写入 `BaselineResult` 前完成，报告只读取
已保存的评分，不承担评分计算职责。

### 3. baseline 与报告入口彻底解耦

CLI 的普通 `--baseline` 分支在打印 JSON 路径后立即返回，不导入或调用报告函数。只有 `-report` 分支读取 1–5 份运行
JSON 并生成报告。这样评测成功不再依赖字体、Matplotlib 或报告目录写入，且不会在运行结束后刷警告。

替代方案是保留自动报告但静默 warning；不采用，因为用户明确不需要自动生成，隐藏警告也会掩盖真实字体错误。

### 4. 一个 Markdown 主文档加相对 PNG 资源

显式报告目录只包含 `report.md` 与 `charts/*.png`。表格按输入顺序每份运行一行，首列且行名只为 manifest 中的 model；
同名模型允许出现重复行，不追加 batch ID。其它列固定为总分、成功率、平均步长、平均执行时长、平均总时长、工具调用
总数、工具失败总数和执行 Token 总数，不含评审 Token。

每个数值指标一张分组柱状图；每份运行是一个柱，同一模型名通过稳定调色板哈希得到相同颜色。Markdown 使用相对路径
引用图片，并在末尾列出输入源路径用于审计，但源路径不进入行名。替代方案是把图片编码进 Markdown；不采用，因为文件
巨大且多数渲染器会限制 data URI。

### 5. 显式发现中文字体并验证字形

报告生成前先验证用户提供的 `artifacts/fonts/Microsoft YaHei.ttf`，不可用时再通过 Matplotlib font manager 按
`PingFang SC`、`Microsoft YaHei`、`Noto Sans CJK SC`、`WenQuanYi Zen Hei` 顺序选择已安装字体，设置
`axes.unicode_minus=False`，并验证常用中文标签字形可用。找不到字体时抛出中文 `ValueError`，且不留下不完整报告
目录；生成测试把 `Glyph missing` warning 视为失败。

实现不下载或修改字体文件；项目字体由用户在本地提供，系统字体作为后备。

## Risks / Trade-offs

- [动作、工具和 Token 参考上限具有经验性] → 固定在 `baseline-score-v1` 并完整写入 JSON；未来调整必须升级版本，禁止静默改分。
- [同名模型多次运行的表格行不可仅凭名字区分] → 保留输入顺序，并在报告末尾列出对应源文件；严格遵守行名仅模型名。
- [缺少 Token 的 provider 无法得到完整总分] → 保留 `null` 与覆盖率，不用零分或动态重加权伪造可比性。
- [部分 Linux 主机没有中文字体] → 显式报错并给出候选字体名称，不生成乱码图片。

## Migration Plan

1. 先在用户明确要求后归档已完成的 `fix-baseline-evaluation-evidence-reporting`，建立可修改的正式 capability。
2. 实现评分模型与 JSON schema。
3. 删除 baseline 完成后的自动报告调用，重写显式 Markdown/PNG 报告。
4. 增加字体发现、评分边界、重复模型名和目录布局测试，并运行 Ruff、相关/完整 pytest 与 OpenSpec 严格校验。
5. 用两份符合当前评分结构的测试记录生成一次显式报告，确认中文、表格和图表；不重跑真实桌面任务。

## Open Questions

无。评分权重、表格行名、评审 Token 排除和 Markdown/PNG 形式均已由用户确认。
