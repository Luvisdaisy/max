## 1. TUI 最终渲染

- [x] 1.1 调整助手消息写入记录区的渲染，使其忽略 `reasoning` 并保留正文与附件摘要。
- [x] 1.2 保持流式区域对思考与正文的分区显示，以及 flush 后对 reasoning 的既有持久化。

## 2. 回归验证

- [x] 2.1 更新流式、多次 think 与工具结果测试，验证流式思考可见而最终助手记录不可见。
- [x] 2.2 更新会话恢复测试，验证含 reasoning 的历史助手消息只显示正文。
- [x] 2.3 运行目标 TUI 测试，以及 `uv run ruff format src tests` 和 `uv run ruff check src tests`。
