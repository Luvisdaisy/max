## 1. 版本化评分与运行 JSON

- [x] 1.1 新增 `baseline-score-v1` 纯评分函数与结构化分项模型，覆盖效果、耗时、步长、工具调用、工具可靠性、执行 Token、安全硬门槛和未知指标。
- [x] 1.2 在每题结束时用任务 timeout 和结果指标计算 score，并将版本、固定参考值、分项、总分、完整性与缺失字段写入 `BaselineResult` JSON。
- [x] 1.3 在批次 summary 中计算 `overall_score`、`score_coverage` 和 `score_version`；任务未覆盖或存在无分项时保持总分为 `null`。
- [x] 1.4 增加公式边界、两位小数、安全违规、环境阻断、未知 Token、完整/不完整批次与 JSON 往返测试。

## 2. 解耦 baseline 与显式报告

- [x] 2.1 删除普通 `max --baseline` 完成后的自动报告导入和调用，使其只写 JSON、打印路径并退出。
- [x] 2.2 调整 `-report` 输入校验与 CLI 文案，使 1–5 份运行 JSON 统一进入多模型 Markdown 报告入口。
- [x] 2.3 删除或收敛不再使用的单次 HTML/source JSON 报告路径，并测试普通 baseline 不创建报告目录或触发 Matplotlib。

## 3. Markdown 多模型表格与柱状图

- [x] 3.1 重构报告加载与聚合：按输入顺序生成模型行，行名只取 manifest model；同名模型保留重复行，源路径放在表格外。
- [x] 3.2 生成只含确认列的 `report.md`：总分、成功率、平均步长、平均执行时长、平均总时长、工具调用总数、工具失败总数和执行 Token 总数，不展示评审 Token。
- [x] 3.3 为每个表格指标生成 `charts/*.png` 多模型柱状图，并用模型名稳定映射颜色，使同一模型跨图颜色一致。
- [x] 3.4 将报告目录限制为一个 `report.md` 与相对引用的 PNG 资源，使用临时目录/原子替换避免失败后留下半成品。

## 4. 中文字体、文档与验证

- [x] 4.1 实现项目微软雅黑优先、跨平台系统字体后备的发现与字形校验，并禁用 Unicode 负号问题。
- [x] 4.2 增加中文图表无 `Glyph missing` warning、无字体清晰失败、同名模型同色、表格无 batch ID/评审 Token 和目录布局测试。
- [x] 4.3 更新 baseline 中文文档，说明不自动生成报告、显式 `-report`、评分公式/版本和字体要求。
- [x] 4.4 运行 `uv run ruff format src tests`、`uv run ruff check src tests`、baseline 相关 pytest、完整 pytest 与 OpenSpec 严格校验。
- [x] 4.5 使用两份构造的当前评分结构 JSON 显式生成报告，核对中文、模型表格、总分和全部柱状图；不得重跑真实桌面任务，并确认源 JSON 未被修改。
