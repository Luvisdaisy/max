## REMOVED Requirements

### Requirement: 受控浏览器 DOM 观察
**Reason**: 交互 Agent 必须复用用户当前桌面 Chrome，不再创建或连接独立的受控 Chrome。
**Migration**: 交互网页观察改用 macOS AX；信息不足时改用既有视觉桌面后备。评测模块的隔离浏览器不受影响。

### Requirement: 浏览器 locator 优先动作
**Reason**: 不再连接用户 Chrome 的 Playwright／CDP 会话，不能使用 locator 操作网页。
**Migration**: 可见 AX 元素经 MacOSAXBackend 操作；其他控件走截图核验后的桌面动作。

### Requirement: 浏览器文件与选项快路径
**Reason**: 该快路径依赖受控页面的 DOM locator。
**Migration**: 通过网页可见控件和 macOS 原生文件选择器完成输入及选择，并按既有桌面动作规则后置观察。
