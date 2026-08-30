# desktop-chrome-reuse Specification

## Purpose
TBD - created by archiving change reuse-desktop-chrome. Update Purpose after archive.
## Requirements
### Requirement: 交互 Agent 复用当前桌面 Chrome

交互 Agent 运行时 MUST NOT 创建、连接、置前、终止或清理任何 Chrome 专属进程、临时 profile 或调试端点。
当用户的 Chrome 位于前台时，系统 MUST 将其视作普通桌面应用，并只通过 macOS AX 或既有视觉桌面工具观察和操作。

#### Scenario: 发送交互任务不新建 Chrome
- **WHEN** 用户在已打开 Chrome 的桌面中向 TUI 发送一项 Agent 任务
- **THEN** 系统不启动独立 Chrome、不中断当前标签页，也不连接 Chrome 调试端口

#### Scenario: 当前 Chrome 缺少 AX 控件
- **WHEN** Chrome 为前台且系统未取得可操作的 macOS AX 元素
- **THEN** Agent 使用当前截图和既有视觉桌面后备，且不创建受控浏览器

