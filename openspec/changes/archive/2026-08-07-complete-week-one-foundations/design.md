## Context

见 `proposal.md`。当前 `max-agent` 已具备 `diagnose`/`/diagnose` 和 `ExperimentArchive`。诊断只检查 PyTorch、CUDA、BF16 与 `pip check`，不能验证第一周所需的 mss、PyAutoGUI、OpenCV、PaddleOCR 与 pynput；其原始 JSON 输出也不利于快速阅读。

## Goals / Non-Goals

**Goals:**

- 用统一的 Doctor 命令验证目标运行时与基础工具，并提供便于人工阅读的结论。
- 在明确授权时，以临时受控窗口验证截图、OCR 和桌面输入的最小闭环。
- 将 README、环境指南和第一周周报收敛到一套 Doctor 命令与交付记录。

**Non-Goals:**

- 不实现通用 OCR、桌面控制、聊天后端、模型服务、数据库或网络回退。
- 不把真实截图、权重、私有运行记录或令牌写入版本控制。
- 不在 Doctor 的配置、环境、轨迹或结果中记录模型型号、目录、远程修订、文件集合或任何派生身份。

## Decisions

### 将文档分为操作指南与周报

README 与 `docs/environment.md` 仅陈述可执行安装和 Doctor 验证步骤；`docs/week1/weekly-report.md` 使用项目约定的周报模板汇总已验证结论、证据路径、限制与第二周前置接口。调研和架构报告继续作为周报引用的来源，不复制其全文。

### 用 Doctor 替换 Diagnose，并提供双层验证

将所有公共入口统一重命名为 `--doctor`、`doctor` 与 `/doctor`，移除旧 `diagnose` 名称而不保留兼容别名。Doctor 的默认层只执行无输入检查：依赖与版本、`pip check`、CUDA/GPU/BF16、mss 的内存截图、OpenCV 的合成图像运算、PaddleOCR 与 pynput 的导入及可用性。结果对象保留逐项状态、详细错误与建议，渲染层按“通过 / 失败 / 跳过”展示简洁摘要；归档时仅写入这些运行时和工具结果，明确排除一切模型相关字段。

显式 `--desktop-probe` 才启动第二层：创建临时受控测试窗口，生成不敏感 OCR 样例，核验截图和 OCR 结果，并在确认该窗口仍是预期目标后发送有限的点击和输入。该层不保存屏幕截图，除非调用者明确选择 ignored artifact 输出；非交互会话、窗口焦点丢失或坐标不匹配时停止，不发送输入。

备选方案是让默认 Doctor 直接点击桌面，或仅检查导入。前者会将输入发送到未知应用，后者不能证明工具链可运行，均不采用。

## Risks / Trade-offs

- [旧文档与实现再次漂移] → 将 README、环境指南、CLI 帮助和周报列为同一变更中的验证项，并用命令帮助与单测核对示例名称。
- [测试期间焦点切换导致输入误投递] → 默认不发输入；显式探针仅操作自建窗口，并在每次输入前检查目标窗口和坐标。
- [PaddleOCR 首次初始化需要下载模型] → 默认 Doctor 只报告本地可用性；完整 OCR 最小示例在显式探针中运行，缺少本地资源时给出清晰失败与安装说明，不隐式下载。

## Migration Plan

1. 以 Doctor 替换 Diagnose，完成默认只读检查和显式受控桌面探针的测试。
2. 替换过时文档示例，补写第一周周报，并执行自动化测试、依赖检查和第一周 Doctor 核验。
3. 回滚时删除 Doctor 增量能力并恢复旧文档；无需迁移持久化数据。
