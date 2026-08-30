## ADDED Requirements

### Requirement: 真实任务完成必须通过可导出门控

系统 SHALL 将 `AgentRunner` 的自然 `done` 与 Online-Mind2Web 任务完成分开。系统 MUST 仅在同一题已成功执行
`task_complete`、已获取完成声明后的独立截图、URL 观察可用且本地 v2 验证通过时写入 `result.json` 并标记
`trajectory_valid`。任一条件不满足时，系统 MUST 不写可提交结果，并写入明确的非成功终态与诊断。

#### Scenario: 模型自然停止但未声明完成

- **WHEN** Agent 返回 `done`，但本题没有成功的 `task_complete` 工具结果
- **THEN** 系统将任务标记为 `model_incomplete`，保留诊断截图且不得生成 `result.json`

#### Scenario: 完成声明和后置截图均有效

- **WHEN** Agent 成功声明完成，后置截图和 URL 均可用，且 v2 验证通过
- **THEN** 系统写入连续步骤的 `result.json`，将任务标记为 `trajectory_valid` 并允许进入 Judge 阶段

### Requirement: 动作预算和运行时阻断必须短路任务

系统 SHALL 仅将会改变网页交互状态的动作计入任务动作预算；截图、定位、OCR、屏幕信息和 hover MUST NOT 消耗
该预算。系统 MUST 在超过预算、跳转未授权域、检测登录/CAPTCHA 或访问拦截页时停止当前 Agent，不得继续模型循环。

#### Scenario: 观察不耗尽动作预算

- **WHEN** Agent 依次调用截图、定位、OCR 和 hover
- **THEN** 任务剩余交互动作预算不变

#### Scenario: 达到交互动作上限

- **WHEN** 已执行的计费交互动作达到安全清单 `max_steps`
- **THEN** 系统中断当前题并记录 `safety_blocked`，不再调用模型或工具

#### Scenario: 站点访问被拦截

- **WHEN** URL 或截图诊断识别出登录、CAPTCHA、Cloudflare 等访问拦截，或 URL 跳出允许域
- **THEN** 系统记录 `environment_blocked` 或 `safety_blocked` 的具体原因，保留已有观察并停止该题

### Requirement: 隔离浏览器必须在执行前可观测

系统 SHALL 在向 Agent 提交任务前确认专用 Chrome 已打开任务起始 URL、URL 位于清单允许域且桌面截图可观察到
该专用浏览器。无法满足任一条件时，系统 MUST 将任务标记为 `environment_blocked`，不得启动 Agent。

#### Scenario: Chrome 进程存在但窗口不可观察

- **WHEN** 专用 Chrome 已启动但前台/截图校验失败
- **THEN** 系统结束该题为 `environment_blocked`，并写入浏览器诊断而不调用模型
