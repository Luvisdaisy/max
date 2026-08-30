## Why

当前 Agent 对浏览器与 macOS 原生界面主要依赖截图、OCR 和坐标键鼠。它虽保留了严格的当前帧、移鼠与后置截图核验，但网页表单、可访问原生控件与文件上传等场景仍让模型承担不必要的坐标推断，速度与稳定性受限。

在明确只覆盖 macOS 原生应用和浏览器的前提下，引入双通道结构化 UI 获取与统一语义工具层，可以优先使用浏览器 DOM 或 macOS 辅助功能接口，视觉坐标仅作为后备，同时复用现有安全与结果验证边界。

## What Changes

- 新增浏览器 UI 后端：从受控浏览器会话提取经筛选的可访问 DOM 元素、当前页面与 URL，并以 locator 优先执行网页动作。
- 新增 macOS 原生 UI 后端：以只读 AX 观察前台应用及元素，在能力与权限允许时以 `AXPress`／`AXValue` 执行原生控件动作；不可用时明确降级。
- 新增帧绑定的统一 `UIElement`／`UISnapshot` 注册表，元素按观察版本短期编号，并标明 `browser`、`macos_ax` 或 `vision` 后端。
- 新增由模型调用的统一语义动作（点击、输入、按键、滚动、拖拽、激活应用、打开 URL、等待、完成），由 Resolver 按元素所属后端分派；保留坐标键鼠作为视觉后备，而不是默认路径。
- 为浏览器文件输入和下拉选择提供受控快路径，并定义网页内容、浏览器原生 UI、系统弹窗之间的通道切换规则。
- 保留并接入当前截图、动作预期、进度和完成证据核验；结构化操作成功不得单独视为任务成功。

## Capabilities

### New Capabilities

- `browser-ui-backend`: 受控浏览器的 DOM 观察、locator 操作与网页专属快路径。
- `macos-ax-ui-backend`: macOS 辅助功能观察、元素解析及受限原生控件操作。
- `semantic-ui-actions`: 帧绑定 UI 注册表、语义动作契约与跨后端分派。

### Modified Capabilities

- `agent-tools`: 默认 Agent 工具从坐标优先扩展为可校验的语义动作，并保留兼容的视觉后备。
- `desktop-gui-tools`: 既有截图与坐标键鼠门禁成为视觉后备路径，并接收统一状态与后置核验。
- `react-agent`: 每轮观察选择浏览器、原生或视觉 UI 上下文，并在语义动作后更新状态与验证。

## Impact

主要影响 `src/max_gui/tools/`、`src/max_gui/desktop/`、`src/max_gui/agent/`、浏览器隔离／调试会话管理与测试替身。预计新增 Playwright 与 macOS `ApplicationServices` 集成；不引入远程浏览器服务，不改变现有会话持久化中的脱敏边界。
