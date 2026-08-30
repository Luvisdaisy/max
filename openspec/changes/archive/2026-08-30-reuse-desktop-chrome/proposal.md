## Why

交互 Agent 会在应用启动时创建临时 profile 的受控 Chrome，并在每个任务首轮观察时将其置前。这会打断用户正在使用的浏览器，也与“直接操作当前桌面”的预期不符。

## What Changes

- 移除交互运行时自动创建、置前和关闭受控 Chrome 的生命周期。
- **BREAKING**：交互 Agent 不再通过 Playwright DOM／locator 观察或操作网页；网页与其他桌面应用一样，统一通过当前前台桌面的 macOS AX 或视觉坐标后备进行观察和操作。
- 让 Agent 保持用户当前 Chrome 的 profile、窗口、标签和前台状态，不创建独立浏览器窗口或标签。
- 保留 Mind2Web 与 WebArena 评测的隔离 Chrome，因为它们的题目隔离和可审计性不属于交互 Agent 会话。

## Capabilities

### New Capabilities

- `desktop-chrome-reuse`: 交互 Agent 复用用户桌面 Chrome，且不创建、置前或终止独立浏览器实例的生命周期契约。

### Modified Capabilities

- `browser-ui-backend`: 交互 Agent 不再依赖受控 Chrome 的 DOM／Playwright 后端。
- `react-agent`: 观察上下文的优先级不再包含受控浏览器页面，改为原生 UI 可用时使用 macOS AX，否则使用视觉后备。
- `semantic-ui-actions`: 网页元素不再标记为 `browser` 后端或分派至 BrowserBackend；保留 macOS AX 和视觉后备的统一语义动作。

## Impact

影响 `src/max_gui/app.py`、`src/max_gui/agent/graph.py`、浏览器后端及相关测试。不会改变用户 Chrome 数据，不新增依赖；隔离评测浏览器模块不在本次改动范围内。
