## Context

`20260829-213226` 的首批真实运行证明：隔离 Chrome 可以启动，模型也会产生工具调用，但评测器没有把“模型自然
停止”“安全动作上限”“站点阻断”“轨迹有效性”和“WebJudge 标签”组织为一个闭环。8 条 ready 任务中，4 条因为
空 action history 被标为 model error，4 条超时；所有任务都没有 `result.json`，也没有 Judge 标签。

现有 `AgentRunner` 的 `done` 是对话控制流终态，不等价于业务完成。现有安全守卫把鼠标移动等桌面动作都计入
步骤上限；`EvaluationStepRecorder` 仅在动作有截图和 URL 时导出，服务层则把所有 v2 验证失败归类为模型错误。
此外 `run_webjudge` 已存在，但 CLI 和 service 没有把它接入真实批次。

约束：不扩大 Agent 的网页感知能力，仍只使用截图和桌面工具；不记录普通运行的键盘正文/reasoning；不绕过
CAPTCHA、登录或安全清单；不修改本地 `--benchmark`。

## Goals / Non-Goals

**Goals:**

- 将单题状态显式拆分为预检、执行、轨迹、Judge 四个阶段，只有通过完成门控的任务可进入 v2 导出与 Judge。
- 在安全或环境条件出现时立即停止当前题，保存诊断并避免无效循环占满超时。
- 将 WebJudge 设为显式可选阶段，真实回填标签、原始输出和错误，并正确表达“未判分”。
- 让报告可区分任务完成、轨迹有效、Judge 成功、环境失败、安全阻断和模型失败。

**Non-Goals:**

- 不自动扩大首批任务安全清单、不添加登录凭据、不绕过 Cloudflare/CAPTCHA。
- 不把模型自然语言声明、无动作回复或仅截图当作任务成功。
- 不提交官方榜单、不把 Judge 结果替代人工截图抽检。

## Decisions

### 1. 使用显式状态机，而不是复用 `ready` 作为执行成功

新增内部任务阶段：`preflight`、`running`、`completed`、`environment_blocked`、`safety_blocked`、
`model_incomplete`、`interrupted`、`trajectory_invalid`、`judge_pending`、`judged`、`judge_error`。
`AgentRunner` 返回 `done` 但没有通过完成门控，服务层一律写为 `model_incomplete`；不再把 v2 的空 action
history 误归为模型异常。

替代方案是仅解析 `AgentState.status`。不采用，因为 `done` 的定义是模型停止，不包含业务完成证据。

### 2. 完成门控以 `task_complete`、后置截图和 v2 验证为连续条件

评测回调记录 `task_complete` 声明；服务层仅在该声明成功、后置独立截图存在、URL 可读且轨迹末步为
`TASK_COMPLETE` 时写 `result.json`。若模型没有请求完成工具、完成工具被安全阻断或后置截图失败，保留临时
截图和诊断，但不生成可提交的 result。

替代方案是从最后一条助手文本推断成功。不采用，因为它不可验证且会让无动作回复进入判分。

### 3. 将安全预算限定为可改变网页状态的动作，并立即短路终态

`mouse_click`、`keyboard_type`、`keyboard_press`、滚动和完成声明占用预算；截图、定位、OCR 和单纯 hover
不消耗预算。每次 URL 检查到未批准域、登录/CAPTCHA、已知访问拦截页，守卫返回结构化终态而不是仅返回一段
错误字符串。编排器收到后中断 Agent，不再让模型重试被阻断的工具。

替代方案是继续用字符串匹配和让模型自行退出。未采用，因为实际运行已出现被阻断后持续循环。

### 4. 独立浏览器启动后必须验证可见性和起始 URL

浏览器适配器启动 Chrome 后，轮询只读 URL 观察器确认初始 URL 位于批准域；桌面层在首张截图前执行前台/窗口
校验。无法确认时不进入 Agent，标记为 `environment_blocked`。不读取 DOM 或执行 CDP 命令。

替代方案是仅相信 `Popen` 成功。未采用，因为进程启动不等于 Agent 实际看见该窗口。

### 5. WebJudge 是明确的批次后处理阶段

CLI 增加显式 Judge 选项与凭据环境变量名；仅收集通过 v2 验证的 `result.json` 后，串行调用一次上游 WebJudge。
解析每题标签和原始输出后回填任务指标；未配置凭据写 `judge_pending`，Judge 进程失败写 `judge_error`。端到端
成功率在没有标签时为 `null`，而不是 0。

替代方案是默认自动 Judge。未采用，因为 Judge 有凭据、成本和外部 API 调用，必须获得显式授权。

## Risks / Trade-offs

- [更严格完成门控会降低可导出数量] → 这是有意的：以无效轨迹换取可审计成功率会误导评测。
- [站点阻断页只能从 URL/截图识别] → 保守归类为环境不可执行，并保留截图供人工抽检。
- [浏览器前台验证跨平台不稳定] → 首期只实现当前 macOS 支持的明确检查，失败即停止且不静默回退。
- [Judge 返回格式变化] → 保存原始输出，并将解析失败单列为 `judge_error`。
- [隔离浏览器与用户前台窗口争用] → 单题串行、每题新 profile，并在任务终止时清理进程。

## Migration Plan

1. 先增加状态机、完成门控、预算分类和单元/集成模拟测试。
2. 增加浏览器初始可见性/URL 校验及环境短路，验证普通 Agent 未启用回调时行为不变。
3. 接通 CLI 到 WebJudge，补齐标签回填和报告口径。
4. 使用安全清单中的单题重新运行；先检查 `result.json`、轨迹截图和报告状态，再显式开启 Judge。
5. 若新路径出现问题，关闭新的显式 Judge 参数即可保留轨迹；不修改历史结果目录或本地 benchmark。

## Open Questions

- 当前 macOS 上“隔离 Chrome 已前台且可由截图看到”的最小可靠检测 API 需要以实际单题验证确认。
- WebJudge 的标签 JSONL 字段与用户选用的评测模型/密钥环境变量需在真实 Judge 前最终确认。
