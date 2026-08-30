## 1. 交互浏览器生命周期

- [x] 1.1 移除 TUI 应用对交互受控 Chrome 与 Playwright 后端的创建、注入和关闭逻辑。
- [x] 1.2 确保交互 Agent 的运行路径不会创建 Chrome 临时 profile、调试端点或置前独立页面。

## 2. 观察与动作通道

- [x] 2.1 将首轮和后置观察调整为仅选择 macOS AX 或视觉后备，并安全作废旧 browser UI 快照。
- [x] 2.2 从交互语义动作分派中移除 BrowserBackend、locator、文件输入和 select 快路径，保留 AX 与视觉回退。

## 3. 验证与说明

- [x] 3.1 更新受影响的单元与集成测试，覆盖不启动 Chrome、当前 Chrome 的 AX 路径、视觉降级和旧快照失效。
- [x] 3.2 运行 `uv run ruff format src tests`、`uv run ruff check src tests` 及相关 pytest；将真实 macOS 冒烟结果与组件测试结果分开记录。
