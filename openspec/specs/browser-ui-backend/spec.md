# browser-ui-backend Specification

## Purpose
TBD - created by archiving change add-dual-channel-ui-backends. Update Purpose after archive.
## Requirements
### Requirement: 交互 Agent 不使用受控浏览器后端

交互 TUI 的 Agent MUST NOT 创建、连接或复用 Playwright／CDP 浏览器后端、临时 Chrome profile 或调试端点。
网页元素信息 MUST 仅来自 macOS AX 或当前截图的视觉后备；独立评测模块的隔离浏览器不受此限制。

#### Scenario: 交互回合不启动受控 Chrome

- **WHEN** 用户在 TUI 提交一条需要网页操作的任务
- **THEN** 交互 Agent 不启动受控 Chrome、临时 profile 或回环调试端点

