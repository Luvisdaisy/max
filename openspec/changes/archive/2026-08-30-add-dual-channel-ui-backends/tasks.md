## 1. 统一 UI 状态与接口

- [x] 1.1 定义 `UIElement`、`UISnapshot`、短期 UIRegistry 与脱敏序列化规则，接入现有任务状态和帧失效逻辑
- [x] 1.2 定义 BrowserBackend、MacOSAXBackend 与 Resolver 协议，并提供可记录调用的 fake 实现
- [x] 1.3 在新观察、通道切换、后置观察、恢复和新任务边界作废旧 `ui_version`／元素引用
- [x] 1.4 为快照版本、元素后端、过期目标与会话恢复补充单元测试

## 2. 受控浏览器通道

- [x] 2.1 增加 Playwright 依赖与仅回环受控 Chrome 的交互会话管理，复用隔离 profile 约束
- [x] 2.2 实现 DOM 可交互元素过滤、语义摘要、当前 URL 观察和内存 locator 注册
- [x] 2.3 实现 locator 点击、双击、填充、滚动、导航、文件输入和选项选择，并为失败提供稳定诊断
- [x] 2.4 覆盖非回环拒绝、DOM 重渲染失效、网页表单和文件上传快路径测试

## 3. macOS 辅助功能通道

- [x] 3.1 实现前台应用／窗口的有限 AX 元素发现、角色映射和权限／读取失败降级
- [x] 3.2 实现前台身份和版本校验后的 `AXPress`／受限 `AXValue` 操作
- [x] 3.3 识别浏览器 chrome、系统权限弹窗与文件选择器，并在其存在时选择 native 通道
- [x] 3.4 覆盖 fake AX、权限不足、前台漂移、元素失效和文件选择器切换测试；在真实 macOS 执行只读冒烟并单独记录

## 4. 语义工具与 ReAct 集成

- [x] 4.1 注册 `click`、`double_click`、`type_text`、按键、滚动、拖拽、激活、导航、等待及浏览器快路径工具 schema
- [x] 4.2 实现按 `element_id`／`ui_version` 分派的 Resolver，禁止模型传入坐标、locator 或后端名称
- [x] 4.3 在 `observe` 中按原生模态、浏览器可用性、视觉后备的顺序选择单一主 UI 通道并注入紧凑摘要
- [x] 4.4 将所有语义副作用接入单副作用批次限制、动作预期、进度验证、后置观察和完成声明门
- [x] 4.5 保留现有坐标工具作为 vision 后备，确认结构化元素动作不会默认触发 PyAutoGUI 路径
- [x] 4.6 覆盖 browser／native／vision 分派、跨通道上传、过期版本和完成证据的 Agent 行为测试

## 5. 文档与验证

- [x] 5.1 更新 README 既定章节中的工具与架构描述，说明结构化通道优先和视觉后备边界
- [x] 5.2 运行 `uv run ruff format src tests` 与 `uv run ruff check src tests`
- [x] 5.3 运行新增及相关 pytest，再运行完整 pytest，并分别记录组件验证与真实 macOS／受控浏览器端到端证据
- [x] 5.4 运行 `openspec validate add-dual-channel-ui-backends --strict`

## 6. 运行时回归修复

- [x] 6.1 在首轮 Think 前完成截图、前台身份和 browser/native UI 快照初始化，使首轮模型 schema 暴露语义工具
- [x] 6.2 受控浏览器 DOM 观察前置受控页面并补充启动时序回归测试，避免 DOM 与截图来自不同浏览器窗口
- [x] 6.3 验证首轮语义工具暴露、受控浏览器集成、完整测试与 OpenSpec 严格校验
