## 1. 调整交互入口

- [x] 1.1 将 `max-agent` 无子命令入口切换为 Prompt Toolkit 主交互控制台。
- [x] 1.2 将 `--chat` 路由到与默认入口相同的 CLI/Prompt Toolkit 交互路径。
- [x] 1.3 明确 `--fallback` 的兼容语义，避免默认实现继续被表述为 fallback；必要时保留兼容别名。
- [x] 1.4 保留 Textual 入口作为显式选择的可选高级 UI，并确保其不成为 CLI 基础交互的硬依赖。

## 2. 稳定命令分发与终端输出

- [x] 2.1 保持 `OperationResult` 和 `dispatch_input` 作为 UI 无关的共享分发契约。
- [x] 2.2 使用 Rich 统一 Prompt Toolkit 主路径中的普通消息、Doctor 结果、错误和退出反馈。
- [x] 2.3 确保 `/doctor`、`/quit`、未知 slash 命令和未配置 AI 后端的行为在主交互路径中保持可测试且不触发模型或桌面控制。

## 3. 测试与兼容性

- [x] 3.1 增加默认入口和 `--chat` 选择 Prompt Toolkit 的 CLI 测试。
- [x] 3.2 增加 Textual 不可用时 CLI/Prompt Toolkit 路径仍可用的测试。
- [x] 3.3 保留现有 Doctor、模型下载、模型校验、离线基准和退出码测试并执行完整测试套件。

## 4. 文档同步与验证

- [x] 4.1 更新 `README.md` 中的默认交互、命令示例和 Textual 定位。
- [x] 4.2 更新 `tech-design.md`、`docs/week1/architecture-report.md`、`docs/week1/weekly-report.md` 及其他命中表述的文档。
- [x] 4.3 运行 `python -m unittest discover -s tests -v`、`python -m pip check`，并核对 OpenSpec 规格验证结果。
