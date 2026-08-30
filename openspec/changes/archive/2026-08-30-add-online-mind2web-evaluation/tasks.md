## 1. 任务与安全契约

- [x] 1.1 新建 `max_gui.mind2web` 包，定义上游任务、安全清单、预检状态、运行 manifest 与汇总的数据模型，并补齐中文模块/公开 API 文档。
- [x] 1.2 实现用户显式任务文件的严格加载与内容摘要，拒绝缺字段、重复 ID、非法 URL 和未授权路径；不得触发网络下载。
- [x] 1.3 实现安全清单校验与可替换的预检接口，区分 ready、站点、登录/CAPTCHA、风险、陈旧和环境状态。
- [x] 1.4 为任务加载、清单、预检分类和零网络保证添加单元测试与本地 JSON fixture。

## 2. 隔离浏览器与执行编排

- [x] 2.1 实现专用 Chrome profile、固定窗口/语言/缩放和仅回环 remote-debugging 启动配置；清理批次临时 profile 而不接触用户浏览器资料。
- [x] 2.2 实现只读 URL 观察器，仅读取专用浏览器当前 tab URL，拒绝 DOM 读取、脚本执行和非回环调试地址。
- [x] 2.3 实现单题与批次编排，直接从任务 `website` 启动既有 `AgentRunner`，支持超时、最大动作数、用户中断与任务间隔离。
- [x] 2.4 实现域名、登录/CAPTCHA 与高后果动作运行时阻断，并将安全/环境终态与模型终态分开。
- [x] 2.5 为浏览器命令构造、URL 观察失败、任务中断、域名阻断和不启用时普通 Agent 行为不变添加模拟测试。

## 3. v2 轨迹导出

- [x] 3.1 为 `AgentRunner` 增加可选的评测步骤回调，仅在评测模式传递已解析的动作、对应观察、URL 和消息关联；保持普通 JSONL 的隐私字段不变。
- [x] 3.2 实现桌面动作到 `HOVER`、`CLICK`、`SCROLL`、`TYPE`、`PRESS_KEY` 与 `TASK_COMPLETE` 的映射，并在同一 ViewFrame 保存点击坐标与截图。
- [x] 3.3 实现输入白名单/敏感模式阻断、最终答案提取和逐题 `result.json`、截图目录写入；上游克隆不得被写入。
- [x] 3.4 实现 Online-Mind2Web v2 本地验证：schema 版本、连续步骤、截图存在、thought、URL、终止动作、答案和 reference length。
- [x] 3.5 为动作映射、截图与坐标绑定、敏感输入、损坏轨迹和普通运行日志无输入正文添加测试。

## 4. WebJudge 与报告

- [x] 4.1 实现显式配置的上游 WebJudge 子进程调用，默认单 worker，通过环境传递评测凭据且不写入文件或日志。
- [x] 4.2 实现任务级与批次级 JSON/Markdown 报告，分开统计计划、ready、环境失败、安全阻断、模型结果、WebJudge、耗时、工具调用、已知 Token 和动作效率。
- [x] 4.3 为未配置凭据、v2 验证失败不调用评测器、Judge 错误、环境分母和未知 Token 添加测试。

## 5. 入口、文档与验证

- [x] 5.1 增加显式 Online-Mind2Web 评测 CLI 入口与帮助文案，不改变现有 `--benchmark` 本地评测入口的行为。
- [x] 5.2 编写中文使用文档，说明数据集访问前置条件、安全清单格式、隔离浏览器、结果目录、WebJudge 配置、人工抽检与真实网站风险。
- [x] 5.3 以用户提供的安全 task id、任务数据和评测凭据完成一次单题真实端到端验证；记录实际环境结果，不把模拟测试当作运行证据。

验证记录：2026-08-30 使用 `ade4c09ad3fdb1607209750924cd232f` 的只读 FlightAware 安全题执行隔离 Chrome 单题；预检 ready、实际执行 75,384ms，模型未调用工具且未声明 `task_complete`，因此结果为 `model_incomplete`，无有效轨迹，未启用 WebJudge。证据位于 `artifacts/evaluations/online-mind2web/20260830-163400/`。
- [x] 5.4 运行 `uv run ruff format src tests`、`uv run ruff check src tests`、相关 pytest 与 `openspec validate add-online-mind2web-evaluation --strict`。
