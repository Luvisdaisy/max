# browser-ui-backend Specification

## Purpose
TBD - created by archiving change add-dual-channel-ui-backends. Update Purpose after archive.
## Requirements
### Requirement: 受控浏览器 DOM 观察

系统 MUST 仅连接由本进程创建、调试端点绑定 `127.0.0.1` 的受控 Chrome 会话。BrowserBackend MUST 从当前 page 提取 URL 和有上限的可交互 DOM 元素；每个元素 MUST 包含角色、短可访问名称、可见性、可用性和边界摘要，MUST NOT 向模型或会话暴露完整 DOM、JavaScript 句柄或 selector。

#### Scenario: 受控页面生成元素快照
- **WHEN** 回环受控 Chrome 的当前页面含可见按钮、链接和文本框
- **THEN** BrowserBackend 返回当前 URL 与这些可交互元素的有限语义摘要

#### Scenario: 非回环端点被拒绝
- **WHEN** BrowserBackend 被配置为连接非 `127.0.0.1` 的调试端点
- **THEN** 系统返回结构化不可用错误，且不得连接该端点

### Requirement: 浏览器 locator 优先动作

对归属 `browser` 的当前有效元素，系统 MUST 优先以 Playwright locator 执行点击、双击、填充、选择、滚动和页面导航。locator 无法解析、元素已失效或操作失败时 MUST 返回结构化诊断；仅当 Resolver 有同一观察版本的视觉后备证据时，才可进入坐标后备。

#### Scenario: 浏览器按钮以 locator 点击
- **WHEN** 当前浏览器快照中的按钮元素有效且模型请求点击
- **THEN** BrowserBackend 调用该元素的 locator 点击，而不调用桌面鼠标后端

#### Scenario: 失效 locator 不直接坐标点击
- **WHEN** 浏览器元素在动作前已从 DOM 消失，且没有当前视觉后备元素
- **THEN** 系统返回元素过期或不可用错误，且不执行坐标点击

### Requirement: 浏览器文件与选项快路径

系统 MUST 为当前有效的 `input[type=file]` 提供文件设置动作，并为原生 `select` 提供选项选择动作。文件路径 MUST 在本地可访问且通过既有工作区／文件策略校验；快路径成功后 MUST 创建后置观察与动作预期，MUST NOT 把文件内容写入状态或模型上下文。

#### Scenario: 文件输入直接设置
- **WHEN** 当前浏览器快照含文件输入且传入的文件路径可访问
- **THEN** 系统使用浏览器文件设置 API，不打开 macOS 文件选择器，并进入后置观察

#### Scenario: 非文件元素拒绝文件设置
- **WHEN** 模型对非文件输入元素调用文件设置动作
- **THEN** 系统返回参数或元素能力错误，且不执行浏览器或桌面操作

