## Why

首批 10 题真实运行中，8 题通过预检却没有任何一题产生合法 `result.json` 或 WebJudge 标签。当前
`end_to_end_success_rate=0.0` 只反映“零个 Judge 成功 / 十个计划题”，并不能说明模型已被判为零分；根因包括
Agent 在未完成网页任务时直接结束、观察动作耗尽安全配额、站点拦截没有及时归类，以及 CLI 没有调用 WebJudge。

需要让 Online-Mind2Web 的运行终态、轨迹导出和判分生命周期对齐，避免把无效轨迹、超时和未判分结果误报为模型
失败或端到端零成功。

## What Changes

- 只将已执行 `task_complete`、获取后置观察并通过 v2 校验的任务视为可导出的完成任务；模型自然停止不再被当作
  成功完成。
- 将动作预算限制在网页交互动作，不让截图、定位和模型观察消耗预算；达到上限、越域、登录/CAPTCHA 或站点访问
  受阻时立即终止当前题并写入明确的安全或环境状态。
- 为隔离浏览器运行增加页面可见性和起始 URL 确认，防止 Agent 在错误的前台应用、阻断页或非授权域上循环。
- 将本地通过 v2 验证的轨迹显式送入 WebJudge，并把每题标签、Judge 错误和未判分状态回填报告。
- 修正汇总口径：模型完成率、WebJudge 成功率、端到端成功率、环境不可执行和安全阻断分别计量；未判分不再伪装为
  0 成功率。

## Capabilities

### New Capabilities

- `online-mind2web-completion-gating`: 定义真实网页任务的完成、失败、中断与可导出轨迹的严格状态机。
- `online-mind2web-judge-lifecycle`: 定义 v2 验证、WebJudge 执行、标签回填和未判分报告语义。

### Modified Capabilities

- 无。Online-Mind2Web 原始能力仍处于未归档 change，本变更以新增的修复契约约束其后续实现。

## Impact

- 影响 `src/max_gui/mind2web/service.py`、`preflight.py`、`trajectory.py`、`report.py`、`webjudge.py` 与 CLI 参数。
- 影响 `src/max_gui/agent/graph.py` 的评测回调与终态暴露，但普通 TUI、JSONL 隐私字段和 `--benchmark` 行为保持不变。
- 新增模拟测试及一次受控单题真实验证；WebJudge 仍只从环境变量读取凭据。
