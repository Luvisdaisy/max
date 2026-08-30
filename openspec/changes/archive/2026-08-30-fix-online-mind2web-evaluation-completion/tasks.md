## 1. 运行终态与完成门控

- [x] 1.1 扩展 Online-Mind2Web 任务指标为预检、执行、轨迹和 Judge 的显式阶段状态，并保持历史结果可读。
- [x] 1.2 在评测回调中记录成功完成声明、后置截图和 URL 关联；模型自然 `done` 未通过门控时标记为 `model_incomplete`。
- [x] 1.3 仅对完成声明、后置截图、URL 与 v2 校验均成功的任务写 `result.json`；为无动作、无完成声明和损坏轨迹保留诊断而非误标模型异常。
- [x] 1.4 为完成门控、普通 Agent 未启用评测回调时行为不变、无效轨迹不写 result 添加单元测试。

## 2. 浏览器安全与环境短路

- [x] 2.1 将动作预算改为只统计 click、scroll、键盘输入/按键和完成声明；截图、定位、OCR、screen_info 与 hover 不消耗预算。
- [x] 2.2 将运行时守卫改为返回结构化安全/环境原因，并在预算耗尽、越域、登录/CAPTCHA 或访问拦截时中断当前 Agent，阻止后续模型循环。
- [x] 2.3 在启动 Agent 前验证专用 Chrome 的初始 URL、允许域和桌面可观测性；失败时写入环境终态并清理 profile。
- [x] 2.4 为预算分类、阻断短路、跨域/登录/Cloudflare 归类、Chrome 不可观察和题间隔离添加模拟测试。

## 3. WebJudge 生命周期与报告

- [x] 3.1 为 CLI 增加显式 Judge 开关、评测模型和凭据环境变量名参数；默认不访问 Judge API。
- [x] 3.2 在批次结束后仅收集已验证的 `result.json`，串行调用 WebJudge，保存原始输出并按 task id 回填标签或 Judge 错误。
- [x] 3.3 修订 JSON/Markdown 汇总，分别统计模型未完成、轨迹有效、Judge pending、Judge error 和已判分任务；无标签时端到端成功率为 `null`。
- [x] 3.4 为未启用 Judge、凭据缺失、Judge 输出解析失败、标签回填和各分母口径添加测试。

## 4. 受控验证与文档

- [x] 4.1 更新中文使用文档，说明完成门控、未判分语义、显式 Judge 参数和站点拦截分类。
- [x] 4.2 使用现有安全清单执行一条允许的真实任务，人工检查浏览器可见性、轨迹、任务终态和报告；若开启 Judge，记录真实凭据外部依赖结果。

验证记录：2026-08-30 使用现有 FlightAware 只读安全清单执行一题。隔离 Chrome 可观察、预检 ready，汇总报告将未完成声明准确归类为 `model_incomplete`，未生成 `result.json` 或有效轨迹；未启用 Judge，端到端成功率保持 `null`。证据位于 `artifacts/evaluations/online-mind2web/20260830-163400/summary.json`。
- [x] 4.3 运行 `uv run ruff format src tests`、`uv run ruff check src tests`、相关 pytest、全量 pytest 与 `openspec validate fix-online-mind2web-evaluation-completion --strict`。
