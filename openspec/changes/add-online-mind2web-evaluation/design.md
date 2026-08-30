## Context

`max-gui` 现有本地 benchmark 通过 Vue 测试场、FastAPI 重置和隐藏业务状态断言评估桌面 Agent。它的
`AgentRunner`、桌面工具、会话和运行 JSONL 已可运行真实截图与键鼠操作，但运行事件刻意不保存输入正文、
坐标和 reasoning，不能事后重建 Online-Mind2Web 所需的逐步轨迹。

上游克隆位于 `artifacts/Online-Mind2Web/`，提供 v2 submission schema、WebJudge 和示例，不包含已获
授权的完整任务清单。Online-Mind2Web 在真实网站执行，必须隔离浏览器状态，并把站点不可用、登录、
CAPTCHA 和安全阻断与模型失败分开。

## Goals / Non-Goals

**Goals:**

- 以不修改上游克隆的方式，加载用户已授权取得的任务数据，并以显式清单选择安全的首批任务。
- 复用 `AgentRunner` 和现有截图/键鼠工具，在固定、隔离的 Chrome 环境从任务指定 URL 执行。
- 在动作发生时原子记录可通过 Online-Mind2Web v2 验证的截图、动作、思考、URL 与最终答案。
- 以独立本地目录保存原始轨迹、运行诊断、WebJudge 标签和汇总，并区分环境、模型与安全结果。

**Non-Goals:**

- 不自动下载受限数据、不自动接受数据集条款、不使用个人账户或绕过 CAPTCHA。
- 不修改、删除或以 Online-Mind2Web 替代当前本地 benchmark；迁移完成前两套能力独立存在。
- 不向 Agent 暴露 DOM、CSS selector、CDP 命令或网页脚本执行能力；只读 URL 采集不属于 Agent 工具。
- 不在首期提交官方榜单、不承诺完成全部 300 题，也不把 WebJudge 当作人类评估的替代品。

## Decisions

### 1. 新建独立 `mind2web` 域，而不是复用本地 benchmark 任务模型

新增 `src/max_gui/mind2web/`，包含任务加载、清单/预检、浏览器编排、步骤记录、v2 导出、WebJudge 调用和
报告。上游任务只有 `task_id`、`website`、`task_description`、`reference_length`，没有本地任务的路由、
初始状态或隐藏断言，强行复用 `BenchmarkTask` 会制造无意义字段和错误成功口径。

替代方案是扩展 `src/max_gui/benchmark/`。不采用，因为它的语义是本地可重置业务场与状态评分，且现有
`open_benchmark_browser()` 只允许回环 URL。

### 2. 任务数据、上游代码和本次结果分离

上游克隆 `artifacts/Online-Mind2Web/` 只读。用户自行取得的任务 JSON 使用显式配置路径；安全清单记录
允许的 `task_id`、首次运行时确认的起始域、最大步骤数和超时。每次运行新建：

```text
artifacts/evaluations/online-mind2web/<run-id>/
  manifest.json
  preflight.json
  trajectories/<task-id>/result.json
  trajectories/<task-id>/trajectory/0000.png
  webjudge/*.jsonl
  summary.json
```

`manifest.json` 固定任务源摘要、上游 commit、模型配置、Chrome 环境、清单摘要和评测器配置。结果不得写回
上游克隆，也不得包含 API Key、Cookie、账号或未脱敏的意外个人输入。

### 3. 显式清单和预检是执行授权边界

加载器只接受用户指定的本地任务文件；不能因为发现任务文件、上游示例或目录中有任务而自动运行。每题先
按清单与当前环境给出 `ready`、`site_unreachable`、`captcha_or_login`、`unsafe_action_risk`、
`task_stale` 或 `environment_error`。只有 `ready` 任务在用户显式启动评测后可以打开外网浏览器。

首期清单仅允许只读、无登录、无上传、无购买/预约/发布/提交的任务。遇到跳转到未批准域、登录、验证码或
高后果操作时，运行器必须停止该题，保留已采集轨迹，并用安全或环境结果标注；这些结果不进入模型失败率。

替代方案是让模型按提示自行判断风险。未采用，因为模型判断不能成为执行真实网站操作的唯一安全边界。

### 4. 以独立 Chrome profile 和只读 URL 观察器执行

编排器为每个批次创建专用 Chrome profile，固定窗口尺寸、缩放、语言和前台状态；任务间清除 profile
状态与标签页。启动地址必须等于任务 `website`，不能先经过搜索引擎。

浏览器以仅绑定 `127.0.0.1` 的 remote debugging 端口启动，URL 观察器只读取当前页面 URL，不读取 DOM、
不执行 JavaScript、不向 Agent 提供接口。若 URL 观察失败，任务可以保留为环境失败而非生成缺失 URL 的
正式轨迹。这样既满足 v2 可审计性，又保持 Agent 的感知与执行仍只有截图和键鼠。

替代方案是 AppleScript 读取 Chrome URL。它不具备稳定的跨环境错误语义，也难以明确绑定专用实例，因此
不作为首选实现。

### 5. 评测步骤在执行时记录，运行日志继续保持隐私最小化

新增仅对评测编排器可见的 `EvaluationStepRecorder` 回调，接收解析后的桌面动作、动作前后截图、只读 URL、
模型关联思考和工具结果。它生成按序号命名的截图与一个自包含步骤；普通 `RunRecorder` 继续只记工具名、
时长、消息索引和安全摘要，绝不因评测需求扩展为记录键盘输入正文或 reasoning。

映射规则：`mouse_move` 为 `HOVER`，`mouse_click` 为 `CLICK`，`mouse_scroll` 为 `SCROLL`，
`keyboard_type` 为 `TYPE`，`keyboard_press` 为 `PRESS_KEY`。`screenshot`、OCR、locate 与
`screen_info` 是观察，不能作为网页动作。点击坐标由完成的 `mouse_move` 在同一 ViewFrame 中解析并保存；
不得从事后文本、缩放截图或 JSONL 推断。

输入文本仅在清单任务要求且不含敏感模式时进入 `TYPE` 描述；其他输入中止导出并标为安全失败。每步均写入
`thought` 键，允许为 `null`，防止 v1 式的数组错位。

### 6. 先在本地验证 v2，再使用上游 WebJudge

导出器在调用上游脚本前验证 schema version、连续 step、截图文件存在、URL、终止 `TASK_COMPLETE`、最终答案
和人类 `reference_length`。验证失败时不调用 WebJudge。WebJudge 运行在独立的用户提供凭据下，默认
单 worker，输出原始判词与标签；报告把 `ready` 任务的 WebJudge 成功率与全部计划任务的端到端结果分开。

替代方案是把模型 `done` 或 `task_complete` 直接视为成功。未采用，因为它没有检查真实网页结果，且违背
Online-Mind2Web 的轨迹判分口径。

## Risks / Trade-offs

- [真实网站更新、地域差异或 CAPTCHA 使结果不可复现] → 每题预检、显式环境状态、冻结任务数据摘要并保留截图。
- [真实操作产生外部后果] → 只读清单、域名约束、浏览器隔离和运行时安全阻断；首期不允许账号态任务。
- [截图与坐标错位导致错误轨迹] → 在动作时保存已解析 ViewFrame 坐标和对应截图，不做事后推断。
- [WebJudge 成本、限流或自动判分误差] → 默认单 worker、保留原始判词、抽样人工复核，并单列 Judge 失败。
- [评测轨迹含敏感输入或页面信息] → 专用无账号 profile、输入脱敏/中止规则、结果目录不自动提交或上传。
- [评测代码扰动普通 Agent 运行] → 评测回调为可选依赖；不启用时 `AgentRunner`、运行日志和工具行为保持不变。

## Migration Plan

1. 用户取得任务数据并人工建立首批只读清单；实现本地加载与 schema/清单测试，不启动浏览器。
2. 实现隔离浏览器、单题编排和结构化轨迹，完成一题人工复核与 WebJudge 读取验证。
3. 完成 10 题安全 smoke，输出环境、模型和安全分类报告；只有真实运行证据齐全后才宣称已接入。
4. 本地 benchmark 保持不变。若用户后续要求弃用它，另建删除/迁移 OpenSpec change，并保留历史报告可读。

## Open Questions

- 首批安全清单的具体 10 个 task id 由用户在取得任务数据后确认；实现不得自行挑选未知真实网站任务。
- WebJudge 使用的模型名、预算和 API endpoint 需在真实运行前由用户配置；首期代码只接受显式配置。
- 若专用 Chrome 的只读 URL 观察器在当前 macOS 权限环境不可用，应记录环境失败并在实现验证后决定是否采用
  AppleScript 降级，而不是静默丢失 URL。
