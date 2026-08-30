## ADDED Requirements

### Requirement: 显式启动的隔离真实网页评测

系统 SHALL 仅在用户显式启动 Online-Mind2Web 评测后，为 `ready` 任务启动独立 Chrome profile。每次运行
MUST 固定浏览器窗口尺寸、缩放和语言，并从任务的 `website` 直接开始，MUST NOT 以搜索引擎或替代网站
作为起点。Agent MUST 继续仅使用现有截图与桌面键鼠工具完成网页操作。

#### Scenario: 按指定起始网站开始任务

- **WHEN** 用户启动一条已预检为 `ready` 的任务
- **THEN** 专用浏览器直接打开任务 `website`，评测器将实际起始 URL 与浏览器环境写入 manifest

#### Scenario: 未显式启动时不访问真实站点

- **WHEN** 系统仅加载任务、生成预检计划或验证轨迹
- **THEN** 系统不得启动外网浏览器、创建模型调用或执行桌面动作

### Requirement: 真实网页风险与环境失败独立终止

系统 SHALL 在任务执行中检测未批准域、登录/CAPTCHA、高后果操作、浏览器崩溃、URL 观察失败、超时和用户
中断。系统 MUST 停止当前题、保留已写入轨迹并以可区分状态结束；环境和安全状态 MUST NOT 计入模型任务
失败率。

#### Scenario: 跳转到未批准域

- **WHEN** 只读 URL 观察器发现当前页面域不属于任务清单批准范围
- **THEN** 系统停止该题并记录安全阻断，不再向 Agent 发出下一轮工具调用

#### Scenario: 用户中断批次

- **WHEN** 用户在批次运行中请求中断
- **THEN** 系统中断当前 Agent，停止后续任务，并写入已完成任务、当前任务终态和批次中断摘要
