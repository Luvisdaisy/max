# 真实桌面基线评测

`max --baseline`（或 `max-gui --baseline`）顺序运行五项 macOS 桌面任务：浏览器检索北京次日天气、
Terminal `whoami`（预期输出 `flkbme`）、Calculator `1+1`、新增内容为「你好我是MAX」的提醒事项，以及向微信文件传输助手发送「你好我是MAX」。

## 启动前提

- 仅支持 macOS，运行终端必须已获得屏幕录制和辅助功能权限。
- `/Applications` 中应有 Google Chrome、Terminal、Calculator、Reminders 和 WeChat。
- 天气任务需要网络；微信必须已登录。
- 所有独立评审固定使用 Qiniu 的 `z-ai/glm-5.3-flash`，启动前必须设置有效的 `MAX_QINIU_KEY`；执行 Agent 可使用其它 provider。
- 开始微信题前，请手动打开「文件传输助手」并确认输入焦点。每题都会向 Agent 开放当前工具注册表中除
  `activate_app`、`click` 外的工具，不再按任务类型增加其它限制；请只在可接受该执行范围时确认开始。
- Qiniu 会收到每题最后一张截图用于独立评审；切换执行 provider 不会改变该边界。若不接受，请不要启动 baseline。

## 运行

```bash
max --baseline
max --baseline --baseline-runs 3
```

启动后、首题确认前，终端会打印当前执行模型的 provider 与 model 名称；该信息不包含端点或 API Key。

命令启动后直接进入第一题，不再要求输入 `RUN_BASELINE`。默认运行一轮；多轮会重复创建提醒与测试消息。
提醒和微信文本均为「你好我是MAX」，系统不会自动删除或撤回，请在评测后自行清理。

每一题开始前，命令会显示该题所需窗口与前置条件。请手动将对应窗口前置并确认状态正确，然后按任意键才会
启动该题的 Agent；按 `Esc` 可跳过当前题，该题会记为安全阻断，不会执行任何桌面动作，也不会消耗提醒或微信的写入预算。

每题仅允许一次个人写入请求，禁止自动重试、恢复重放或在截图评审失败后再次执行。

每题 Agent 的执行阶段最多运行 5 分钟或执行 20 次逻辑模型调用，以先到者为准；provider 在单次逻辑调用内的重试和
后续独立评审 AI 均不计入 20 次额度。达到调用额度时记录 `model_limit`；达到 5 分钟时先温和中断，5 秒内未收尾则
强制取消，并记录 `timeout` 或 `timeout_forced`。两种上限终止后都会截取当前桌面并自动进入独立评审。任务文件中的
`timeout_seconds` 固定为 300，同时作为执行终止值和时间评分参考。普通 GUI 动作不设数量上限，且不再执行任务专用
violation 判定；工具参数校验、确认门和 Agent 通用执行约束仍然生效。

执行期间，当前终端会依次显示实际发送给 Agent 的完整任务提示词、模型正文，以及每个工具步骤的工具名、参数、
成功或失败状态、结果文本和截图路径。模型只返回工具调用而没有正文时仍会显示工具步骤。控制台不会注册或显示
模型的 reasoning/思考增量，也不会直接打印包含思考字段的会话消息或事件载荷。

每题只使用一张终态截图进行无工具的独立评审；评审固定使用 Qiniu 注册配置，与执行 Agent 的 provider/model 隔离。
`z-ai/glm-5.3-flash` 不支持关闭思考，因此评审请求固定发送 `thinking.type=enabled` 和
`reasoning_effort=low`；客户端不注册 reasoning 输出回调，终端不会显示其思考过程。
评审最多总尝试三次，在无流式输出的可重试错误时指数退避，并在
执行结束后冷却，以降低与执行模型争抢 RPM 配额的概率。评审限流会标为 `review_error`，不伪造成任务未完成。
调用评审 AI 前，终端会显示 provider、model、完整评审文本和终态截图路径；收到响应后会显示原始评审正文，格式
无效时也会先显示原文再记录错误。终端不会显示 API Key、Authorization、截图二进制或 base64 编码。

```bash
max --baseline -report artifacts/evaluations/baseline-desktop/<timestamp>.json
max --baseline -clean
```

普通 baseline 完成后只写运行 JSON，不会自动生成报告或加载 Matplotlib。只有显式使用 `-report` 才会读取 1–5 份
运行 JSON，并在 `artifacts/evaluations/baseline-desktop-reports/` 生成一个 `report.md` 和相对引用的
`charts/*.png`。表格每次运行一行，行头只显示模型名；列为总分、成功率、平均步长、平均执行/总时长、工具调用总数、
工具失败次数和执行 Token 总数，不包含评审 Token。同一模型在所有图中使用相同颜色。

图表优先验证并使用项目内的 `artifacts/fonts/Microsoft YaHei.ttf`；该文件不可用时，再检查 PingFang SC、
Microsoft YaHei、Noto Sans CJK SC、WenQuanYi Zen Hei，以及 macOS 自带的 Hiragino Sans GB、Heiti SC 或
Arial Unicode MS。没有覆盖中文标签的字体时，报告会明确失败且不留下半成品。
`-clean` 仅清空 `artifacts/evaluations/baseline-desktop/`，不会删除共享运行 JSONL、会话或截图目录。

## 结果与口径

结果仅写入 `artifacts/evaluations/baseline-desktop/<timestamp>.json`，其中包含执行与评审 provider/model、逐题结果、执行模型调用次数、Token、
耗时、步长、终态、独立评审、截图与运行日志引用，以及 `baseline-score-v2` 总分、分项和固定参考值。结果结构不包含
violation 字段。
上述任务提示词、模型正文、工具参数/结果与评审原始输入输出仅用于当前控制台核对，不会新增到该结果 JSON。

端到端成功仅以截图评审为 `pass` 为准；Agent 完成声明仅作诊断，不会否决可见证据。权限、应用、登录或用户确认缺失
属于环境/安全阻断，不进入模型失败率。未知 Token 维持 `null`，不会按零汇总。

单题总分为 0–100 分：效果 70 分，执行时间 10 分，动作步长、工具调用、工具可靠性和执行 Token 各 5 分。
时间以题目 timeout 为参考；动作、工具调用和执行 Token 的参考上限分别为 10、15 和 100000。评分不包含 violation
硬门槛；环境或用户确认阻断不评分；必需效率指标未知时总分为 `null`。完整批次只在所有任务均有总分时保存平均总分，并始终
保存评分覆盖率。基础模型与 Windows LoRA 模型比较时，必须使用相同任务文件、轮次数、屏幕条件、提示词和 provider
配置；当前仓库不会自动恢复已移除的旧 remote provider。
