## ADDED Requirements

### Requirement: 显式启动的五题 macOS 基线评测

系统 SHALL 支持 `max --baseline` 与 `max-gui --baseline` 启动版本化的五题 macOS 基线评测。任务集 MUST
包含天气检索与汇报、输出必须为 `flkbme` 的 `whoami` Terminal 命令、Calculator `1+1`、文本为
「你好我是MAX」的 Reminders 新建和向 WeChat 文件传输助手发送相同文本；每题 MUST 配置执行提示词、截图 rubric、超时、动作预算
和风险等级。该入口 MUST NOT 改变 `--benchmark` 的行为。

#### Scenario: 启动默认单轮基线评测
- **WHEN** 用户执行 `max --baseline`
- **THEN** 系统不得要求输入批次级确认词，并按任务文件的稳定顺序逐题等待人类确认目标窗口已前置，再为已确认的题目使用配置的执行提示词

#### Scenario: 每题等待窗口前置确认
- **WHEN** 系统即将开始任一基线任务
- **THEN** 系统显示该题所需前台窗口和前置条件，并等待人类按任意键继续；在确认前不得调用执行模型或执行桌面动作

#### Scenario: 保持现有 Web 评测入口
- **WHEN** 用户执行 `max --benchmark`
- **THEN** 系统仍仅启动原有本地 Web 评测首页，不加载或运行基线桌面任务

### Requirement: 受控的环境预检与个人写入预算

系统 MUST 在每题调用模型前执行 macOS 平台和个人写入预算预检，但 MUST NOT 以固定应用安装路径、网络或账号
状态阻断任务；这些状态由人类前台窗口确认和最终截图证据判断。T4 和 T5 MUST 视为 `personal_write`，每题每轮
只允许一次写入请求，禁止自动重试、恢复重放和评审失败后的再次执行。多轮数必须由用户显式提供。

#### Scenario: 人类未确认当前题
- **WHEN** 当前题的窗口前置确认被取消或拒绝
- **THEN** 系统将该题记录为 `safety_blocked`，不调用模型、不消耗个人写入预算，并继续处理后续已确认的任务

#### Scenario: 人类确认微信已前置
- **WHEN** T5 即将运行
- **THEN** 系统仅展示 WeChat 文件传输助手的人工确认提示，不读取登录或联系人状态；独立截图评审仍只依据最终截图决定是否通过

#### Scenario: 多轮写操作需要逐题确认
- **WHEN** 用户请求超过一轮的基线评测
- **THEN** 系统不显示批次级确认词，但每一题都必须等待对应窗口的人工确认

### Requirement: 最终截图的独立无工具评审

每题 Agent 执行结束后，系统 MUST 在存在最终截图时恰好发起一次独立、无工具的评审模型调用。评审输入 MUST
仅包含任务 ID、版本化截图 rubric、运行日期和最终截图，MUST NOT 包含 Agent 最终文本、完整对话、reasoning
或工具轨迹。评审输出 MUST 解析为 `pass`、`fail` 或 `indeterminate`，并保存有限的可见证据与原因；无截图
或解析失败不得伪造为通过。

#### Scenario: 评审不采纳 Agent 自我声明
- **WHEN** Agent 声称任务完成，但最终截图未显示任务 rubric 要求的可见证据
- **THEN** 评审结果为 `fail` 或 `indeterminate`，该题不得计入截图评审通过数

#### Scenario: 每题仅评审一次
- **WHEN** 一题已保存最终截图且执行结束
- **THEN** 系统只发送一次无工具评审请求，并分别记录执行与评审的耗时、模型标识及 Token 用量

#### Scenario: LLM 调用失败时重试
- **WHEN** 执行或截图评审 LLM 调用在未产生流式内容前遇到可重试失败
- **THEN** 系统最多总尝试 3 次，并使用指数退避；耗尽后记录错误与尝试次数，当前题输出失败但不重放 Agent 轨迹

### Requirement: 可审计的逐次指标与多轮可视化

系统 MUST 为每个批次输出不可覆盖的 manifest、逐题结果、最终截图、评审结果、JSON、Markdown 和离线
HTML dashboard。逐题结果 MUST 记录任务/提示词版本、round ID、模型配置摘要、环境状态、终态、Agent 完成
声明、评审 verdict、执行/评审/总耗时、模型/工具/动作统计、违规、Token 及证据引用；未知 Token 和未知数值
MUST 保留为 `null`。dashboard MUST 按任务和模型显示多轮的样本数、成功/环境阻断/评审 verdict、耗时、动作、
工具失败、已知 Token 和终态分布。

#### Scenario: 多轮结果保留未知 Token
- **WHEN** 多轮中的部分执行或评审调用未返回 Token 用量
- **THEN** 对应逐题字段为 `null`，汇总只报告已知样本与已知总量，不得将未知值按零计入图表或平均值

#### Scenario: 离线查看多轮 dashboard
- **WHEN** 一个基线批次完成至少两轮
- **THEN** 用户打开结果目录的 `dashboard.html` 即可离线查看按任务和模型分组的逐轮指标与样本数，无需启动服务或访问外网

### Requirement: 基线 JSON 对比报告与受限清理

系统 SHALL 支持 `max --baseline -report <summary.json>...`，输入数量 MUST 为 1–5，读取各批次汇总 JSON 并输出
合并 JSON、Markdown 与 Matplotlib PNG 图表；图表 MUST 标明样本数和未知值。系统 SHALL 支持
`max --baseline -clean`，且 MUST 只删除项目 `artifacts/evaluations/baseline-desktop/` 内的内容，不得删除共享运行、
会话或截图目录。

#### Scenario: 生成多份 JSON 的可视化报告
- **WHEN** 用户携带 1–5 个有效的基线 `summary.json` 执行 `max --baseline -report`
- **THEN** 系统为每份输入生成可追溯的比较记录，并写出成功率与平均执行时长图表及 Markdown 报告

#### Scenario: 拒绝超过五份输入
- **WHEN** 用户向 `-report` 提供超过 5 个 JSON
- **THEN** CLI 以参数错误退出，不读取或写入报告

#### Scenario: 清理仅限基线目录
- **WHEN** 用户执行 `max --baseline -clean`
- **THEN** 系统清空基线评测目录内容并保留目录本身，且共享运行、会话和截图目录保持不变
