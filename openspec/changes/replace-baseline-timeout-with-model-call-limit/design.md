## Context

baseline 已用 `max_iterations` 限制逻辑模型调用，并恢复了 5 分钟墙钟时长上限。
`AgentRunner` 在每次逻辑模型响应后递增 iteration，运行记录器也以 `model.started` 统计逻辑模型调用；provider 内部重试
不会增加该计数。任务专用 guard 和 violation 数据链路已移除，本次保持该边界不变。

## Goals / Non-Goals

**Goals:**

- 单题最多运行 5 分钟或执行 20 次 Agent 逻辑模型调用，以先到者为准。
- 所有任务使用固定 Qiniu provider/model 评审，与执行配置隔离。
- 每题向模型暴露当前注册表中除 `activate_app`、`click` 外的全部工具，删除任务专用 guard 和 violation 数据链路。
- baseline 启动时输出执行 provider/model，便于在产生桌面副作用前核对实际配置。
- 独立评审、普通 TUI 和其它评测保持现有调用额度与工具策略。
- 保留耗时指标，并继续用任务时间参考值计算效率分项。

**Non-Goals:**

- 不取消每题开始前的用户窗口确认或个人写入轮次预算。
- 不取消工具参数校验、单工具 timeout、一次回复单副作用等通用 Agent 约束。
- 不把独立评审调用或 provider 内部重试并入执行 Agent 的 20 次额度。
- 不修改 baseline 五题内容和独立截图评审 rubric。

## Decisions

### 1. 复用 `max_iterations=20` 作为逻辑模型调用额度

baseline 构造专用 settings 时覆盖 `max_iterations=20`。每题创建独立 Agent 与会话，从 iteration 0 开始；每次逻辑模型
响应后 iteration 增加一次，准备发起第 21 次调用前由现有上限检查停止。推理重试发生在单次 `client.stream()` 内，独立
评审使用另一个客户端，因此两者都不会占用额度。

达到上限时把现有迭代上限错误规范为 baseline `model_limit` 终态。相比在 baseline 通过事件回调另建计数器，复用 Agent
循环的单一控制点不会产生调用已发出但计数尚未更新的竞态。

### 2. 使用 5 分钟墙钟上限并在终止后继续评审

baseline 用独立 task 运行 `runner.run()`，并用 `asyncio.wait_for(asyncio.shield(...), 300)` 等待。5 分钟到点后先调用
`runner.interrupt()`，再给 Agent 5 秒收尾并持久化摘要；收尾仍未完成时取消协程。前者记录 `timeout`，后者记录
`timeout_forced`。无论哪种超时终态，都继续取得编排器终态截图并进入评审，不把执行超时当作跳过评审的条件。

五题任务 JSON 的 `timeout_seconds` 统一改为 300，并继续作为 `baseline-score-v2` 时间分项参考值。若 Agent 先达到 20 次
逻辑调用，则正常返回 `model_limit` 并进入相同的截图和评审链路；临界竞态以编排器先观察到的终态为准。

### 3. 为 AgentRunner 增加默认关闭的完整工具开关和可选排除集合

`AgentRunner.run(expose_all_tools=True)` 时，Think 节点使用 `registry.names()` 生成 schema，并可通过默认空的
`excluded_tools` 排除指定名称；默认值为假时，普通运行仍使用截图、AX、恢复状态驱动的动态工具集合。baseline 显式开启
完整工具模式并排除 `activate_app`、`click`，因此这两个工具既不出现在模型 schema，也不属于 Act 节点允许集合。

Act 节点既有参数校验、通用恢复和副作用批次约束继续生效，这些属于所有 Agent 的执行契约，不产生 baseline violation。

`run_baseline()` 在参数校验后、Qiniu 评审配置校验和首题确认前打印执行 `provider` 与 `model`；该输出只展示非敏感配置，
不包含端点或 API Key。

### 4. 完整删除 violation，并从工具步骤统计动作

删除 `_guard`、`BaselineStatus.VIOLATION`、`BaselineResult.violations`、`BaselineScore.safety_violation` 及评分硬门槛参数。
成功只由独立评审 `pass` 决定。动作数改由 `_BaselineConsoleTrace.on_tool_step()` 按动作工具名计数，使控制台输出与指标仍共享
同一实际工具步骤来源。删除硬门槛改变了评分语义，因此算法版本升级为 `baseline-score-v2`；用户已确认清理旧数据，
不提供旧版本兼容分支。

### 5. 启动时构造统一 Qiniu 评审配置

`run_baseline()` 从 provider 注册表取得 Qiniu 定义，读取并校验 `MAX_QINIU_KEY`，再基于执行 `Settings` 创建一份独立评审
settings：固定 `provider=qiniu`、注册表模型和端点、Qiniu 上下文窗口，为强制思考模型开启 thinking 并把
`reasoning_effort` 固定为 `low`，同时保留最多三次评审请求。执行 settings
不被修改；同一份评审 settings 传给五题，保证不同执行 provider/model 的结果都由同一裁判评估。

评审客户端不注册 reasoning 输出回调，只消费最终正文，因此强制思考不会出现在 baseline 控制台。该模型不支持
`thinking.type=disabled`，显式使用最低推理档位既满足上游契约，也避免落入默认 `max` 档位。

缺少 Qiniu 密钥时在任何桌面任务开始前直接报现有中文凭据错误，避免先产生个人写入再发现评审不可用。运行 manifest
同时记录执行与评审的 provider/model。评审仍创建独立客户端且 `tools=None`，其调用与重试不进入执行会话的
`model_calls`。

## Risks / Trade-offs

- [单次 provider 调用可能卡住] → 5 分钟墙钟上限与有限收尾窗口保证编排器随后进入截图评审。
- [受控工具集合仍扩大 Agent 可执行范围] → 排除 `activate_app`、`click`，每题仍需用户确认前台窗口，工具自身校验和通用 Agent 约束保留。
- [温和中断可能无法及时收尾] → 5 秒后强制取消并记录 `timeout_forced`，仍保留编排器截图和可用摘要。
- [删除 violation 使新 JSON 与旧结构不同] → 用户已确认会清理旧数据，不提供旧记录兼容。
- [统一 Qiniu 评审依赖云端凭据和可用性] → 启动前校验 `MAX_QINIU_KEY`，运行记录明确评审 provider/model，错误如实保存。

## Migration Plan

1. 更新正式 capability delta、AgentRunner 开关和 baseline 数据模型。
2. 实现 5 分钟与 20 次调用竞速终止及固定 Qiniu 评审，补充超时后仍进入评审、配置隔离、完整工具和无 violation 测试。
3. 更新中文说明并运行 Ruff、相关/完整 pytest、OpenSpec strict。
4. 不自动迁移或清理旧 JSON；回滚时恢复本变更前代码即可。

## Open Questions

无。5 分钟墙钟上限、20 次额度范围、固定 Qiniu 评审、完整注册工具和 violation 删除范围均已由用户确认。
