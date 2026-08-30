# 真实桌面基线评测

`max --baseline`（或 `max-gui --baseline`）顺序运行五项 macOS 桌面任务：浏览器检索北京次日天气、
Terminal `whoami`（预期输出 `flkbme`）、Calculator `1+1`、新增内容为「你好我是MAX」的提醒事项，以及向微信文件传输助手发送「你好我是MAX」。

## 启动前提

- 仅支持 macOS，运行终端必须已获得屏幕录制和辅助功能权限。
- `/Applications` 中应有 Google Chrome、Terminal、Calculator、Reminders 和 WeChat。
- 天气任务需要网络；微信必须已登录。
- 开始微信题前，请手动打开「文件传输助手」并确认输入焦点。Agent 不会点击、搜索或切换联系人，只可发送本轮
  固定文本「你好我是MAX」。
- 云端 provider 会收到每题最后一张截图用于独立评审。若不接受这一边界，请先切换至你信任的本地 provider。

## 运行

```bash
max --baseline
max --baseline --baseline-runs 3
```

命令启动后直接进入第一题，不再要求输入 `RUN_BASELINE`。默认运行一轮；多轮会重复创建提醒与测试消息。
提醒和微信文本均为「你好我是MAX」，系统不会自动删除或撤回，请在评测后自行清理。

每一题开始前，命令会显示该题所需窗口与前置条件。请手动将对应窗口前置并确认状态正确，然后按任意键才会
启动该题的 Agent；按 `Esc` 可跳过当前题，该题会记为安全阻断，不会执行任何桌面动作，也不会消耗提醒或微信的写入预算。

每题仅允许一次个人写入请求，禁止自动重试、恢复重放或在截图评审失败后再次执行。

每题 Agent 的执行阶段最长为 3 分钟，普通 GUI 动作不设步数上限；Terminal、提醒事项和微信的安全输入限制仍然
生效。执行超时后系统会先请求 Agent 收尾，再截取当前桌面作为终态证据。

每题只使用一张终态截图进行无工具的独立评审；评审最多总尝试三次，在无流式输出的可重试错误时指数退避，并在
执行结束后冷却，以降低与执行模型争抢 RPM 配额的概率。评审限流会标为 `review_error`，不伪造成任务未完成。

```bash
max --baseline -report artifacts/evaluations/baseline-desktop/<timestamp>.json
max --baseline -clean
```

`-report` 可携带 1–5 份运行 JSON，在 `artifacts/evaluations/baseline-desktop-reports/` 生成合并 JSON、
Markdown 以及成功率和平均时长 PNG 图表。`-clean` 仅清空 `artifacts/evaluations/baseline-desktop/`，不会删除共享
运行 JSONL、会话或截图目录。

## 结果与口径

结果仅写入 `artifacts/evaluations/baseline-desktop/<timestamp>.json`，其中包含参数、逐题结果、Token、耗时、步长、
终态、独立评审、截图与运行日志引用。自动生成的 HTML、Markdown 与图表输出到独立的
`artifacts/evaluations/baseline-desktop-reports/<timestamp>/`。

端到端成功要求未触发安全违规且截图评审为 `pass`；Agent 完成声明仅作诊断，不会否决可见证据。权限、应用、登录或
用户确认缺失属于环境/安全阻断，不进入模型失败率。未知 Token 维持 `null`，不会按零汇总。

`dashboard.html` 可离线打开，按任务和多轮样本显示成功率、评审结论、执行耗时、动作数、工具失败、已知 Token
和终态分布。基础模型与 Windows LoRA 模型比较时，必须使用相同任务文件、轮次数、屏幕条件、提示词和 provider
配置；当前仓库不会自动恢复已移除的旧 remote provider。
