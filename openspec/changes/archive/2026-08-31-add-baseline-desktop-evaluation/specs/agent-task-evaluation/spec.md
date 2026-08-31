## ADDED Requirements

### Requirement: 基线桌面评测结果与 Web 评测报告隔离

系统 SHALL 允许基线桌面评测复用通用原子指标定义，但 MUST 将其任务文件、运行目录、环境状态、截图评审
结果与跨运行 dashboard 同现有 Web GUI benchmark 报告隔离。基线环境/安全阻断 MUST 不计入模型失败率；
Web benchmark 的任务数、首页选择和成功率分母 MUST 保持既有语义。

#### Scenario: 基线环境失败不污染 Web 报告
- **WHEN** 一次基线评测因 WeChat 未登录将 T5 标为 `environment_blocked`
- **THEN** 基线报告单独统计该状态，既有 Web GUI benchmark 的报告、结果目录和成功率不包含该任务
