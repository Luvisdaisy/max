## Context

现有运行时以 `think → act → observe` 为主循环，默认工具通过 PyAutoGUI 使用截图视图像素执行桌面键鼠。正在进行的状态层变更已把前台身份、有限 UI 候选、动作预期和进度绑定到最新观察帧，但候选没有后端 locator，也不能分派结构化动作。

本变更限定为 macOS 原生应用与受控 Chrome 会话。浏览器评测现有的 CDP 会话只读取 URL；它不提供 DOM 观察或网页控制。macOS 当前只使用 AppKit／Quartz 读取前台身份，并有限读取 Dock AX 元素。两类结构化 UI 通道都需要保留明确的权限、进程归属和时效边界。

## Goals / Non-Goals

**Goals:**

- 让网页内容优先使用 Playwright locator，原生可访问控件优先使用 AX 操作，视觉坐标仅处理两类结构化通道不足的界面。
- 让模型调用小而稳定的语义工具，使用当前 `UISnapshot` 内短期 `element_id`，不暴露坐标或后端私有 locator。
- 复用当前帧失效、单副作用、动作预期、进度和独立完成证据规则。
- 把浏览器网页内容、浏览器原生 chrome、系统对话框的通道选择做成可测试的确定规则。

**Non-Goals:**

- 不支持 Safari、Firefox、跨平台桌面、用户已有浏览器 profile 或远程浏览器服务。
- 不构建完整 AX 树持久化、跨帧元素追踪、复杂视觉目标检测或通用工作流引擎。
- 不删除现有坐标工具，也不允许结构化 locator 绕过工具确认、任务完成或后置验证。
- 不把密码、完整 DOM、完整 AX 树、键盘输入正文、文件内容或可执行 locator 写入会话。

## Decisions

### 1. 引入短生命周期的统一 UI 快照

定义内部 `UIElement` 和 `UISnapshot`：元素含短期 ID、角色、短名称／文本、能力、可见性、所属应用／窗口、`backend` 与仅进程内保存的 locator。快照含单调递增版本、来源 `ViewFrame` 与 `ui_context`（`browser`、`native`、`vision`）。模型调用带 `element_id` 和 `ui_version`；版本不匹配或元素不存在返回稳定的过期错误，不执行动作。

选择每次观察重新编号而不是跨帧稳定 ID，因为现有系统已经把可执行视觉定位绑定到当前帧；这可避免窗口、DOM 重渲染与弹窗出现后复用陈旧对象。会话只保存可脱敏摘要，不保存 locator。

### 2. 浏览器只连接受控的回环 Chrome

新增 BrowserBackend，复用隔离 Chrome 的回环 CDP 限制，以 Playwright 连接专用调试端口。观察时只提取当前 page 的 URL 和有限可交互元素（button、link、输入、选择、checkbox、radio、tab、menuitem 等）的 role、可访问名称、可见／可用状态和边界摘要。DOM 及 locator 只存内存。

网页动作依序使用 `locator.click()`、`fill()`、`select_option()`、`set_input_files()` 等结构化操作；仅 locator 不可用、元素属于自绘内容或操作失败并有当前视觉证据时，才回退到既有坐标路径。与仅通过 CDP 自行发协议相比，选择 Playwright 以获得稳定 locator、自动等待与可测试 API；引入依赖的成本由隔离会话约束抵消。

### 3. macOS AX 后端只处理原生 UI

新增 MacOSAXBackend，以 `NSWorkspace` 找前台应用、`AXUIElement` 读取窗口与有限可交互元素。元素 locator 包含受验证的 pid 和短期 AX 路径／引用；执行前须确认当前前台 app／window 仍匹配快照。动作优先 `AXPress`，可编辑字段优先受限 `AXValue`；不可执行或无权限时返回诊断状态，交由视觉后备，不猜测。

选择 AX 优先而非 CGEvent 坐标，因为它不依赖 Retina、窗口位置或遮挡。CGEvent／PyAutoGUI 仍承担 vision 后备和 AX 不支持的拖拽类动作，并继续受现有移鼠截图门禁约束。

### 4. 明确浏览器内容、原生 chrome 与系统弹窗的选择顺序

观察首先取得只读前台身份与截图。当前前台为受控 Chrome、Playwright page 可用且没有原生模态对话框时，选择 browser 快照；出现文件选择器、权限弹窗、下载 UI 或浏览器 chrome 时选择 native 快照。无可用结构化快照时选择 vision 快照。每次通道切换都创建新版本，作废上一通道元素。

这比同时向模型呈现两套元素更节省上下文，也能避免网页与原生同名控件混淆。文件上传先检测 file input 并使用 `set_input_files`；不存在时才走网页点击→原生文件选择器→网页后置验证的跨通道流程。

### 5. 首轮 Think 前建立观察基线

运行新任务或恢复任务时，Agent MUST 在首轮 Think 前先刷新一张当前截图，并完成一次前台身份与结构化 UI 观察。若受控浏览器可用且不存在原生模态窗口，浏览器页先置前再截图，确保 DOM 快照与模型看到的截图属于同一窗口；否则继续按 native／vision 顺序降级。观察失败不得阻断任务启动，但必须保留视觉后备；受控 Chrome 启动的操作系统错误统一转换为可降级的运行时错误并清理临时 profile。

### 6. 语义工具替代默认坐标编排，但保留兼容后备

模型默认得到 `click`、`double_click`、`type_text`、`press_key`、`press_shortcut`、`scroll`、`drag`、`activate_app`、`open_url`、`wait`、`set_file_input`、`select_option` 和 `task_complete`。所有目标型动作使用 `element_id`／`ui_version`。Resolver 按元素 backend 分派：browser 走 BrowserBackend，macos_ax 走 MacOSAXBackend，vision 以受现有门禁保护的坐标后备执行。

现有 `mouse_*`、`keyboard_*` 仍作为内部视觉后备和兼容工具，而非结构化浏览器／AX 的首选路径。每个真实副作用都登记既有 expectation，并要求新观察；工具返回成功只代表分派成功，不能直接推进任务完成。

## Risks / Trade-offs

- [Playwright 连接失败或浏览器不受控] → 仅接受回环隔离 Chrome；返回不可用状态并回退到 native／vision，不连接用户浏览器。
- [AX 权限、动态树或元素失效] → 每次操作重新确认前台身份和快照版本；诊断为未知或过期，不重试陈旧 locator。
- [浏览器内容与系统对话框竞争] → 原生模态优先，并在每次观察时重新选择通道。
- [语义工具扩大操作面] → 目标必须绑定当前快照；所有副作用仍受单动作批次、后置观察与完成声明门约束。
- [DOM／AX 内容含敏感信息] → 上下文与会话仅保留有限短标签和摘要，locator／完整树仅进程内暂存。
- [新增 Playwright 依赖和 macOS 专有代码] → BrowserBackend 通过协议和 fake 实现测试；非 macOS 返回明确不支持，不影响现有桌面工具。

## Migration Plan

1. 定义 UIElement、UISnapshot、UIRegistry 和 fake 后端，接入当前状态层的帧失效规则。
2. 为隔离 Chrome 增加 Playwright 观察／操作，并覆盖 DOM 快照、失效、网页表单和文件上传快路径。
3. 增加只读 AX 元素树与受限 `AXPress`／`AXValue`，覆盖权限不足、前台漂移和系统文件选择器。
4. 新增语义工具与 Resolver，逐步调整 Agent schema 和系统提示，保留坐标后备兼容测试。
5. 在 fake browser／fake AX、回环浏览器和真实 macOS 权限环境分别验证；回滚时不注册语义后端，现有 PyAutoGUI 工具链保持可用。

## Open Questions

- 交互 CLI MUST 新建独立受控 Chrome 会话，使用临时 profile、回环调试端口并由 `max-gui` 生命周期管理；MUST NOT 复用 Mind2Web 评测会话。
- `activate_app` 是否仅允许白名单的浏览器和前台应用？建议首版限制为已观察到的应用，避免按任意名称启动进程。
- `drag` 的 AX／浏览器兼容范围是否首版只支持 browser locator 和 vision 坐标后备？建议如此，原生复杂拖拽留待后续提案。
