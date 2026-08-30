# agent-recovery-guardrails Specification

## Purpose
TBD - created by archiving change harden-agent-loop-and-session-records. Update Purpose after archive.
## Requirements
### Requirement: 坐标边界错误触发帧重置恢复
当桌面移动、拖拽或滚动因坐标超出当前 `ViewFrame` 而失败时，Agent MUST 记录该错误与当前帧标识，清除该帧的猜测坐标，并在再次分发同类桌面动作前要求成功 `screenshot` 或使用绑定当前帧的 `target_id`。同一帧中重复提交同一越界参数 MUST 被本地拒绝为结构化恢复错误，MUST NOT 调用桌面后端。

#### Scenario: 越界坐标后不能原样重试
- **WHEN** `mouse_move` 因 `tool_error` 返回坐标超出当前视图
- **THEN** 下一次使用相同坐标和同一帧的 `mouse_move` 被拒绝，并提示先刷新截图或使用当前帧定位编号

#### Scenario: 新截图解除旧帧限制
- **WHEN** 越界失败后成功取得一张新的截图
- **THEN** Agent 可以针对新帧请求合法视图像素的移动

### Requirement: 重复未命中定位必须切换观察策略
对同一当前帧、同一规范化 `query` 和 `region` 的 `locate`，连续两次返回无项目时，Agent MUST 阻止第三次相同调用，并在模型上下文中要求改用空查询、不同区域、OCR 或新截图之一。空查询的完整候选输出在同一帧内最多允许一次。

#### Scenario: 同一 Chrome 查询两次未命中
- **WHEN** 当前帧内两次 `locate(query="Chrome", region="dock")` 都返回空项目
- **THEN** 第三次同参数调用不触发定位工具，且下一次 think 获得切换观察策略的中文原因

#### Scenario: 空查询只执行一次
- **WHEN** 当前帧已经成功执行过空查询 locate
- **THEN** 再次对同一帧执行空查询被拒绝，并提示使用已有编号或刷新截图

### Requirement: 重复失败必须有终止诊断
Agent MUST 为同一失败指纹维护连续次数。达到配置的恢复上限仍未取得新的成功观察或有效桌面进展时，Agent MUST 以 `error` 结束，并在会话与运行摘要中写入 `recovery_exhausted`、失败工具、错误码和次数。

#### Scenario: 连续恢复耗尽
- **WHEN** Agent 对同一帧连续触发达到恢复上限的坐标或定位失败
- **THEN** 不再请求模型或分发同类工具，终态为 `error` 且保存结构化失败原因

