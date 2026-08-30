## MODIFIED Requirements

### Requirement: ReAct 观察选择单一主 UI 通道

每个 `observe` MUST 先获得前台身份和截图，再按以下顺序选择一个主 UI 上下文：存在原生模态对话框时选择
`native`；否则当前前台应用存在可操作的 macOS AX 元素时选择 `native`；否则选择 `vision`。系统 MUST 将选中的
有限 UI 快照、版本和状态摘要注入下一次 `think`，MUST NOT 创建、连接或置前受控浏览器页面。

#### Scenario: 当前 Chrome 有 AX 控件
- **WHEN** Chrome 为前台、没有原生模态对话框且取得可操作的 macOS AX 元素
- **THEN** 下一次 `think` 得到 native UI 快照摘要，且系统不连接 Playwright 页面

#### Scenario: 原生弹窗覆盖网页上下文
- **WHEN** Chrome 前台但观察到文件选择器
- **THEN** 下一次 `think` 得到 native UI 快照摘要而非网页元素列表

### Requirement: 通道动作触发统一后置观察

MacOSAXBackend 和视觉后备的每一个成功副作用 MUST 经 `observe` 创建新观察、更新或作废 UI 快照，并用既有
expectation／progress 机制判断动作效果。通道不可用或动作失败 MUST 向下一次 `think` 提供不含敏感定位信息的
恢复诊断。

#### Scenario: AXPress 后快照刷新
- **WHEN** AXPress 成功执行
- **THEN** Agent 进入 `observe`，旧 AX 元素失效并依据新观察验证动作预期
