## Context

`max` 和 `max-gui` 已指向同一 CLI，当前 `--benchmark` 用回环网页、隐藏业务状态和 10/100 条任务评测
Agent；它不覆盖浏览器联网检索、Terminal、Calculator、Reminders 或 WeChat 等真实 macOS 桌面场景。
现有 `AgentRunner` 已提供运行 JSONL、最终状态、截图、工具统计和已知 Token 用量，但没有任务级独立
截图评审，也没有跨运行趋势图。

本变更新增的 5 条任务含网络、提醒事项和微信自发消息。它们的环境状态、个人写入和外部页面变化都不能被
误计为模型失败；多次运行也不能静默重复产生提醒或消息。

## Goals / Non-Goals

**Goals:**

- 让用户通过 `max --baseline`（兼容 `max-gui --baseline`）显式启动 5 条版本化 macOS 基线任务。
- 使每条任务拥有固定的执行提示词、前置检查、预算、任务专属截图评审提示词和可机器读取的成功契约。
- 在 Agent 停止后只额外调用一次无工具评审模型，依据最终截图和任务 rubric 独立给出 `pass`、`fail` 或
  `indeterminate`。
- 将逐题、单轮和多轮指标、截图引用、环境状态与评审结果持久化；生成离线 HTML 可视化和 JSON/Markdown
  报告，以便比较同条件的基础模型与 LoRA 模型。

**Non-Goals:**

- 不替代现有 `--benchmark` 的回环 Web 评测，不改变其 10/100 首页选择、任务或报告语义。
- 不使用 AppleScript、Shell、DOM/CDP 或进程/数据库查询来替 Agent 完成任务；评测器只能做预检、调用
  Agent、保存证据和读取用户已授权的最小验收状态。
- 不把截图评审视为绝对真值；不可见、遮挡或无法确认的证据必须为 `indeterminate`。
- 不自动删除提醒或撤回微信消息；清理由用户完成，系统在报告中保留本轮运行编号，但不修改用户指定的固定文本。

## Decisions

### 1. 新建独立的 `baseline` 领域和版本化任务文件

新增 `src/max_gui/baseline/` 与 `artifacts/benchmarks/baseline-desktop-v1.json`。任务模型包含稳定 ID、执行
提示词、评审提示词、前置条件、风险等级、动作/时长限制、环境检查项与成功证据规则。首版任务为：

1. 在浏览器搜索北京执行日期次日的天气并汇报来源、日期、天气、最高/最低温和降水信息。
2. 在 Terminal 通过 GUI 输入并观察 `whoami` 的精确输出 `flkbme`。
3. 在 Calculator 计算 `1+1`。
4. 在 Reminders 新建固定文本「你好我是MAX」且不设置重复或通知。
5. 在已登录的 WeChat「文件传输助手」发送固定文本「你好我是MAX」。

任务不是扩展 `BenchmarkTask`：后者依赖回环页面路由、可重置初始状态和隐藏业务断言；真实桌面任务需要
环境预检、风险信息和截图证据。替代方案是继续用手工文档记录 5 题，不采用，因为无法统一提示词、结果
结构、模型对比和可视化。

### 2. `--baseline` 是真实副作用的显式授权与多次运行边界

CLI 新增 `--baseline`，默认运行一轮，启动后不再要求输入批次级 `RUN_BASELINE`。可选次数参数必须显式给出。
每题开始前，CLI 必须显示目标窗口和前置条件，等待
人类将窗口前置后按任意键继续；未确认的单题记为 `safety_blocked`，不调用模型或执行桌面动作。每题运行前再
执行 macOS 与个人写入预算预检。应用安装、登录、网络和前台窗口均由人类确认与最终截图证据负责，不进行硬编码
应用路径或账号状态检查。

T4/T5 是 `personal_write`：运行器禁止自动重试、恢复重放或在评审失败后重做；同一运行内只允许一次发送或
新建请求。T1 允许联网但不允许登录、购买、下载或提交表单；T2 命令固定并在任务定义中白名单。

替代方案是用假网页替代所有任务；不采用，因为目标是补齐真实桌面原型的基础验收。每题均由人类确认窗口已
前置；该确认只授权开始当前题，不放宽既有个人写入护栏。

### 3. 执行与评审分成两个独立的模型调用

每题先以任务执行提示词运行既有 `AgentRunner`。只有任务已取得最终截图，才创建全新、无工具的
`InferenceClient` 评审请求，输入仅为任务 ID、版本化 screenshot rubric、运行日期和最后一张截图；不传
Agent 的最终声明、完整对话、reasoning 或工具轨迹。评审输出必须是严格 JSON：`verdict`、`visible_evidence`
和 `reason`，三者均有长度上限；解析失败或未取得截图为 `review_error`/`indeterminate`。

最终题目成功的主口径为：环境 ready、执行未触发安全/预算终态、Agent 产生完成声明，且评审 verdict 为
`pass`。报告同时保留 `agent_claimed_complete` 与 `review_verdict`，避免把任一方单独冒充真实成功。

执行和独立评审的每一次 LLM 调用均最多尝试 3 次（首次与最多 2 次重试），仅在未产生任何流式输出时采用指数
退避重试；错误摘要、尝试次数和最终终态写入逐题结果。用户选择云端 provider 时，截图会发送至该用户已配置的
服务；该事实在每题窗口确认提示中显示。

### 4. 统一指标、不可变运行目录与本地 HTML 可视化

每个批次写入 `artifacts/evaluations/baseline-desktop/<batch-id>/`：

```text
manifest.json
runs/<round-id>/<task-id>/result.json
runs/<round-id>/<task-id>/final-screenshot.png
runs/<round-id>/<task-id>/review.json
summary.json
summary.md
dashboard.html
```

`result.json` 记录任务/提示词版本、round ID、执行与评审模型、环境状态、终态、Agent 完成声明、评审结论、
端到端耗时、执行/评审耗时、模型调用、工具调用/失败、动作数、违规、已知执行/评审/合计 Token、运行 JSONL
和截图引用。未知数值为 `null`，绝不写作 0。manifest 记录 macOS 版本、显示分辨率/缩放、任务文件 hash、
CLI 参数和不可含密钥的 provider 摘要。

`dashboard.html` 由 Python 标准库生成，内嵌原始汇总 JSON 与 SVG/CSS：按任务和模型显示每轮 verdict、
成功率、环境阻断数、执行耗时分布、动作/工具失败、已知 Token 以及终态分布。无需引入 JavaScript 框架或
图表服务；样本数不足时明确显示 `n`，不输出虚构置信结论。

每题结束即增量写入 `result.json`，启动时预留唯一批次目录；最终汇总只能复用该预留目录，不能再次创建它。每题
完成独立截图评审后，CLI 输出「成功」或「失败」及稳定原因。`max --baseline -report <summary.json>...` 最多接收
5 份批次 `summary.json`，生成横向成功率与平均耗时的 Matplotlib PNG、合并 JSON 和 Markdown 报告；空或未知值
明确标注。`max --baseline -clean` 只清空 `artifacts/evaluations/baseline-desktop/`，不触及共享运行 JSONL、会话或
截图目录。

### 5. 可测试的最小环境适配器与证据边界

抽象只读 `BaselineEnvironment`：检查屏幕录制/辅助功能、应用可用性、网络、Chrome/Terminal/Calculator/
Reminders/WeChat 前置状态和「文件传输助手」身份。测试用 fake 适配器和 fixture 截图验证任务选择、写入
护栏、独立评审请求、结果聚合和 SVG/HTML；真实 macOS 验证只由用户明确执行，不进入 CI。

任务评审不得读取窗口标题、OCR 全文、Reminder 数据库、WeChat 本地数据库或系统进程列表来决定成功；这些
仅允许作为环境预检或用户可见的最小前台身份诊断。最终证据仍以 Agent 取得的截图为主。

## Risks / Trade-offs

- [天气页面随时间、地域或广告变化] → rubric 只要求可见来源与目标日期信息，记录执行时间、来源与
  `indeterminate`，不写死天气数值。
- [云端评审泄露桌面截图] → 启动前显示 provider 风险；只上传最终一张任务截图，不上传会话/轨迹；用户可
  改用本地 Ollama。
- [多轮重复写入相同个人文本] → 默认一轮、每题人工窗口确认、每题一次写入预算，且不自动重试 Agent 轨迹。
- [微信登录、提醒权限或辅助功能缺失] → 人工确认窗口前置和最终截图证据；未确认或 Agent 失败均明确记录，不能伪造成功。
- [截图评审幻觉或界面遮挡] → 独立无工具评审、`indeterminate`、保存可人工复核截图，且不以模型文本取代证据。
- [真实桌面状态导致跨题污染] → 任务开始前记录前置状态；只要求无数据破坏的最小变更，不承诺自动系统回滚。

## Migration Plan

1. 添加任务 JSON、数据模型、CLI 帮助与 fake 环境/评审测试；不运行真实桌面。
2. 接入执行护栏、最终截图评审、结构化结果和单轮报告，验证模拟任务链路。
3. 在用户已确认的 macOS、微信登录和权限环境执行一轮，人工检查 5 个证据目录与清理提示。
4. 以显式轮次数运行基础模型与 Windows LoRA 模型，使用生成的 dashboard 对比；README 只记录真实运行过的
   结果，不把模拟测试当作指标。

## Open Questions

- Windows LoRA 模型在当前已移除 `remote` provider 的运行时如何被选为执行模型，需在真实比较前确定；本
  变更不擅自恢复已删除 provider。
- 评审是否必须使用不同于执行模型的 provider 仍由用户决定；首版允许相同模型但单独调用并明确记录。
