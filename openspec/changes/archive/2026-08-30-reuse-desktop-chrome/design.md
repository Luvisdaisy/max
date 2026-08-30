## Context

交互 TUI 在挂载时创建 `ControlledChromeSession`，并把它注入 `PlaywrightBrowserBackend`。每个 Agent
任务的首轮观察会让该页面置前，以便 DOM 快照和截图一致；这导致用户工作中的 Chrome 被打断。Mind2Web
与 WebArena 的隔离 Chrome 由独立模块管理，仍依赖临时 profile，不属于本设计。

## Goals / Non-Goals

**Goals:**

- 交互 Agent 不启动、连接、置前或关闭任何 Chrome 进程。
- 用户已打开的 Chrome 与其他应用统一由 macOS AX 观察；AX 不可用或信息不足时保持现有截图、定位和键鼠
 视觉后备。
- 移除交互 BrowserBackend 后，仍保留现有单步操作、后置观察和完成核验边界。

**Non-Goals:**

- 不尝试连接用户 Chrome 的远程调试端口，不读取 DOM、标签历史、Cookie 或 profile 数据。
- 不改变评测模块的隔离浏览器，也不新增浏览器扩展、CDP 或 Playwright 替代方案。
- 不承诺通过 AX 获取所有网页元素；网页控件不可见时使用既有视觉路径。

## Decisions

### 1. 完全移除交互 BrowserBackend 注入

`MaxGUIApp` 不再持有或启动 `ControlledChromeSession` 和 `PlaywrightBrowserBackend`，并在退出时不处理
Chrome 生命周期。保留模块是否删除由实现阶段依据引用与测试范围决定，但交互运行路径不得实例化它们。

备选方案是保留受控 Chrome 但不置前；DOM 与用户当前屏幕会失去同一性，且独立窗口仍会出现，因此拒绝。

### 2. 观察仅选择原生或视觉上下文

每次观察先取得前台身份、AX 元素与截图：原生模态优先，其次是可用的 macOS AX 元素，否则为 vision。
不再为浏览器调用 `bring_to_front()`。现有 `UIElement`／`UISnapshot` 数据可在实现中收敛为 AX 和 vision
后端，过渡期读取旧 `browser` 持久化数据时安全作废。

备选方案是让用户每次手动附加 Chrome 调试端口；这仍会读取用户 profile，扩大隐私与配置复杂度，因此拒绝。

### 3. 网页操作复用安全的桌面动作链

AX 能提供当前 Chrome 元素时，语义动作经 `MacOSAXBackend` 执行；否则模型按现有截图、定位、移鼠、截图
核验和键鼠工具操作。此设计不把网页操作视作安全例外，继续沿用桌面风险控制与后置观察。

## Risks / Trade-offs

- [网页控件的 AX 信息不足] → 自动降级到现有视觉后备，并在下一轮状态中保留不可用诊断。
- [失去 DOM 文件上传和 select 快路径] → 通过用户可见的网页控件和原生文件选择器完成，测试覆盖该降级路径。
- [旧会话存有 browser 快照] → 恢复时作废旧快照，要求重新观察，绝不复用 locator。
- [误改评测隔离逻辑] → 按模块区分测试，评测 Chrome 生命周期保持不变。

## Migration Plan

1. 移除交互应用的 Chrome 生命周期及 BrowserBackend 注入，调整观察与语义分派。
2. 删除或隔离已不可达的交互浏览器代码和测试，补充 AX／视觉回归测试及“不会启动 Chrome”测试。
3. 运行静态检查与测试；真实 macOS 验证只记录“不新建 Chrome、可操作当前前台 Chrome”的结果。
4. 若需回滚，恢复本变更前的交互 Chrome 生命周期与 browser 通道；评测路径无需迁移。

## Open Questions

- 无。用户已明确选择复用日常 Chrome，而非保留独立受控会话。
