# max-gui macOS 桌面基准评测收尾报告

评测日期：2026 年 8 月 31 日

任务版本：`baseline-desktop-v1`

评分版本：`baseline-score-v2`

## 一、结论摘要

本报告评估的不是模型独立回答问题的能力，而是模型驱动 `max-gui` GUI Agent 在真实 macOS 桌面上观察界面、调用工具、完成任务并留下可见结果的能力。评测使用 5 个执行模型，每个模型运行同一组 5 项任务，共得到 25 个“模型 × 任务”样本；本批次 25 项前置检查均通过，没有环境阻断或安全阻断，评分覆盖率为 100%。

本批次的独立截图评审结果为 9 项 `pass`、12 项 `fail`、4 项 `indeterminate`，没有评审服务错误，整体任务成功率为 36.0%。`qwen3.8:latest` 表现最好，5 项任务通过 4 项，成功率 80.0%，平均总分 69.90；`z-ai/glm-5.3-flash` 通过 3 项，成功率 60.0%，平均总分 64.56；`qwen3.5:4b` 通过 2 项，成功率 40.0%。`qwen3-vl:8b` 与 `qwen3.5:9b` 在本轮均未获得 `pass`。

这里的“成功”只表示最终截图中的可见证据满足该题验收规则。模型自行声明完成、Agent 执行终态和截图验收是三类不同信息：即使执行终态为 `agent_error`、`model_limit` 或 `timeout`，只要终态截图已经呈现正确结果，仍可判为成功；反过来，即使 Agent 正常结束并声明完成，只要截图不能证明结果，也不计成功。

## 二、评测目标与适用范围

该基准用于回答三个问题：

1. GUI Agent 能否在真实桌面环境中完成一组基础的观察、输入和应用操作任务。
2. 最终桌面状态是否提供了足以独立验收的可见证据。
3. 在效果之外，不同执行模型的耗时、动作、工具调用、工具失败和 Token 成本有何差异。

评测覆盖浏览器、Terminal、Calculator、Reminders 和 WeChat 五类常见桌面场景，同时包含只读任务与个人写入任务。它适合比较当前任务集和当前桌面条件下的模型表现，不用于证明模型具备通用桌面自动化能力，也不用于单独评估视觉定位、点击精度或每一步动作的原子正确率。

本批次比较的执行配置如下：

| 执行 provider | 执行模型 | 独立评审 provider | 独立评审模型 | 轮次 | 单题模型调用上限 | 单题执行时限 |
| --- | --- | --- | --- | ---: | ---: | ---: |
| Qiniu | `z-ai/glm-5.3-flash` | Qiniu | `z-ai/glm-5.3-flash` | 1 | 20 | 300 秒 |
| Ollama | `qwen3-vl:8b` | Qiniu | `z-ai/glm-5.3-flash` | 1 | 20 | 300 秒 |
| Ollama | `qwen3.8:latest` | Qiniu | `z-ai/glm-5.3-flash` | 1 | 20 | 300 秒 |
| Ollama | `qwen3.5:9b` | Qiniu | `z-ai/glm-5.3-flash` | 1 | 20 | 300 秒 |
| Ollama | `qwen3.5:4b` | Qiniu | `z-ai/glm-5.3-flash` | 1 | 20 | 300 秒 |

五次运行的平台均为 `macOS-26.5.2-arm64-arm-64bit`，使用相同任务文件；任务文件 SHA-256 均为 `5718ffc74834a5c255943dcfdc86d6b17240ce3403940621f8215b6312ff04f4`。

## 三、五项任务定义与验收标准

每项任务都由“前置条件、发送给 Agent 的任务提示、风险级别、截图验收规则和 300 秒时限”组成。下表给出了阅读和复现本评测所需的完整任务定义。

| 任务 | 风险 | 前置条件 | Agent 必须完成的操作 | 独立截图验收方式 |
| --- | --- | --- | --- | --- |
| `weather` | 只读 | 网络可用；浏览器可启动；不得登录或提交表单 | 在浏览器中搜索北京天气；必须依据搜索结果中的可见信息汇报，不得凭记忆回答；查看最终截图后结束任务 | 截图必须清楚显示北京的天气预报信息；信息不可见或被遮挡时判为 `indeterminate` |
| `terminal` | 只读 | Terminal 可启动 | 仅运行 `whoami`；观察输出精确为 `flkbme` 后结束任务；不得输入其他命令 | 截图必须同时显示 Terminal、命令 `whoami` 和精确输出 `flkbme`，否则判为 `fail` 或 `indeterminate` |
| `calculator` | 只读 | Calculator 可启动 | 在 Calculator 中完成 `1+1=2`；仅在最终截图清楚显示结果 `2` 后结束任务 | 截图必须显示 Calculator 和结果 `2`；数字无法辨认时判为 `indeterminate` |
| `reminders` | 个人写入 | Reminders 可启动；用户授权创建一条个人提醒 | 新建标题为“你好我是MAX”的提醒；确认最终截图显示完整标题后结束任务 | 截图必须显示 Reminders 中完整提醒标题“你好我是MAX”，否则判为 `fail` 或 `indeterminate` |
| `wechat` | 个人写入 | WeChat 已登录；用户已手动打开文件传输助手 | 在文件传输助手中发送“你好我是MAX”；最终截图可见该文本后结束任务 | 截图必须同时显示文件传输助手和完整文本“你好我是MAX”；无法确认收件人或文本时判为 `indeterminate` |

天气任务只要求搜索并显示“北京天气”的可见预报信息，没有限定必须是次日天气，也没有规定温度、天气现象等字段必须全部出现。该边界以任务版本 `baseline-desktop-v1` 的实际提示词和验收规则为准。

## 四、运行环境与启动前提

评测只能在 macOS 上执行。运行终端需要获得屏幕录制和辅助功能权限，系统中需要安装并能够打开 Google Chrome、Terminal、Calculator、Reminders 和 WeChat。天气任务依赖网络；WeChat 必须已经登录，并由用户提前打开文件传输助手。

独立截图评审固定使用 Qiniu 的 `z-ai/glm-5.3-flash`，因此运行前必须提供有效的 `MAX_QINIU_KEY`。执行 Agent 可以使用其他 provider 和模型，但切换执行模型不会改变评审模型。

每道题启动前，CLI 会提示用户把对应窗口切到前台并再次确认前置条件。用户按任意键后才开始执行；按 `Esc` 会跳过当前题，并记为 `safety_blocked`。程序自身的自动预检只验证当前系统是否为 macOS，以及个人写入是否得到授权；它不会读取应用数据库、账号、联系人或其他个人数据，因此应用是否已启动、账号是否登录、窗口是否正确均由用户确认和最终截图共同负责。

`reminders` 和 `wechat` 会产生真实个人写入。每轮最多各执行一次，系统禁止同轮自动重试或恢复重放，但不会自动删除提醒或撤回微信消息，评测结束后需要人工清理。

## 五、一次任务如何执行

每个模型按照 `weather → terminal → calculator → reminders → wechat` 的固定顺序运行。单题流程如下：

1. 读取版本化任务定义，为当前轮次生成唯一标识，并显示任务前置条件、执行模型、模型调用上限和时限。
2. 等待用户把目标窗口前置并确认；用户拒绝或按 `Esc` 时不调用模型，直接记为安全阻断。
3. 检查 macOS 和个人写入预算；检查未通过时记为环境阻断或安全阻断，不进入模型失败率。
4. 创建新的 Agent 会话，向 Agent 发送该题完整提示词。Agent 可以使用当前注册表中除 `activate_app` 和 `click` 外的工具；动作工具、参数校验、确认门和 Agent 通用约束继续生效。
5. Agent 执行到正常结束、出现错误、达到 20 次逻辑模型调用或达到 300 秒，以先发生者为准。provider 在一次逻辑调用内部的重试不额外占用 20 次额度。
6. 达到 300 秒时先请求 Agent 温和中断；5 秒内仍未收尾则强制取消。对应执行终态分别记录为 `timeout` 或 `timeout_forced`。达到模型调用上限记录为 `model_limit`。
7. 执行终止后重新截取当前桌面，优先把这张 `post_termination_snapshot` 作为终态证据；如果截取失败，才回退到 Agent 最后一张有效观察截图。
8. 等待 60 秒冷却后，把单张终态截图、执行日期和该题专用验收规则发送给独立评审模型。评审模型不获得工具，也看不到 Agent 的完成声明，只能依据截图中的可见内容判断。
9. 保存执行状态、评审结论、截图来源、运行日志、耗时、动作、模型调用、工具调用、工具失败、执行 Token、评审 Token 和评分分项，最终生成一份原子 JSON 运行记录。

普通 GUI 动作没有单独的数量硬上限；“平均步长”是报告指标和评分输入，不是终止条件。

## 六、独立验收与成功判定

评审模型必须且只能返回以下三个结论之一：

- `pass`：截图中存在足以确认任务目标已经完成的可见证据。
- `fail`：截图中的可见状态不满足任务目标，或能够确认结果错误。
- `indeterminate`：截图缺失、被遮挡、模糊，或无法确认目标窗口、收件人、文本等关键证据。

评审输出采用严格 JSON，字段固定为 `verdict`、`visible_evidence` 和 `reason`；额外字段、Markdown 代码围栏或非法值都会被视为评审格式错误。评审请求最多总尝试三次，仅对尚未产生流式输出的可重试错误进行指数退避。全部尝试失败时记录原始 `review_error`，不会伪造成截图验收失败。

单题成功条件为：

```text
success = 前置检查为 ready 且 review_verdict == pass
```

实际实现中，只有进入执行阶段的 `ready` 任务才进入成功率分母；环境阻断和安全阻断不算模型失败。`agent_claimed_complete` 仅用于诊断，不是成功门槛。执行终态也不直接决定成功，因此“Agent 正常结束”不等于“任务成功”，“Agent 执行报错”也不必然等于“任务失败”。

## 七、总分如何计算

`baseline-score-v2` 为每个已测量任务计算 0–100 分，总分由六个分项相加：

| 分项 | 权重 | 计算方式 |
| --- | ---: | --- |
| 效果 | 70 | `pass` 得 70 分；`indeterminate` 得 35 分；`fail`、无截图或评审错误得 0 分 |
| 执行时间 | 10 | `10 × clamp(1 - 执行毫秒数 / 300000)` |
| 动作步长 | 5 | `5 × clamp(1 - 动作数 / 10)` |
| 工具调用 | 5 | `5 × clamp(1 - 工具调用数 / 15)` |
| 工具可靠性 | 5 | `5 × clamp(1 - 工具失败数 / max(工具调用数, 1))` |
| 执行 Token | 5 | `5 × clamp(1 - 执行 Token / 100000)` |

其中 `clamp` 会把结果限制在 0–1。耗时、动作、工具调用和 Token 越少，效率分越高；超过参考值后对应分项最低为 0，不产生负分。

总分与成功率表达不同含义：成功率是严格的任务通过比例，只有 `pass` 才算成功；总分允许 `indeterminate` 获得 35 分效果分，并继续累计效率分。因此不能用“总分大于某个值”替代任务成功判定。任一必需效率指标缺失时，单题总分保持 `null`；只有同一批次全部任务都有完整总分时，才计算模型平均总分。本批次五个模型的评分覆盖率均为 100%。

## 八、五模型总体结果

| 模型 | 总分 | 成功率 | 通过任务数 | 平均步长 | 平均执行时长（毫秒） | 平均总时长（毫秒） | 工具调用总数 | 工具失败次数 | 执行 Token 总数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `z-ai/glm-5.3-flash` | 64.56 | 60.0% | 3/5 | 4.60 | 48090 | 112866 | 29 | 0 | 160107 |
| `qwen3-vl:8b` | 26.46 | 0.0% | 0/5 | 9.60 | 159576 | 224813 | 72 | 11 | 457491 |
| `qwen3.8:latest` | 69.90 | 80.0% | 4/5 | 7.60 | 178224 | 244214 | 53 | 2 | 293961 |
| `qwen3.5:9b` | 21.82 | 0.0% | 0/5 | 13.60 | 51296 | 114759 | 83 | 14 | 475644 |
| `qwen3.5:4b` | 52.10 | 40.0% | 2/5 | 10.00 | 28810 | 92327 | 69 | 11 | 373768 |

`qwen3.8:latest` 的成功率和总分均为最高；它通过天气、Terminal、Calculator 和 WeChat，仅 Reminders 在达到 300 秒后验收失败。`z-ai/glm-5.3-flash` 通过天气、Terminal 和 Reminders，但其 5 项执行中有 4 项记录为 `agent_error`，说明终态截图效果与 Agent 运行稳定性必须分开解读。`qwen3.5:4b` 通过 Terminal 和 Calculator；另外两个模型本轮没有通过任务。

25 项执行终态中，10 项为 `completed`、9 项达到 `model_limit`、5 项为 `agent_error`、1 项达到 `timeout`。这组分布说明本批次不仅存在截图效果差异，也存在明显的执行收敛和运行稳定性差异。

## 九、逐题验收结果

下表按“独立评审结论 / 执行终态”展示每个样本。前者决定是否成功，后者用于诊断执行过程。

| 模型 | Weather | Terminal | Calculator | Reminders | WeChat |
| --- | --- | --- | --- | --- | --- |
| `z-ai/glm-5.3-flash` | `pass / agent_error` | `pass / completed` | `fail / agent_error` | `pass / agent_error` | `fail / agent_error` |
| `qwen3-vl:8b` | `indeterminate / model_limit` | `fail / completed` | `fail / agent_error` | `fail / model_limit` | `indeterminate / model_limit` |
| `qwen3.8:latest` | `pass / completed` | `pass / completed` | `pass / completed` | `fail / timeout` | `pass / completed` |
| `qwen3.5:9b` | `indeterminate / model_limit` | `fail / completed` | `fail / model_limit` | `fail / model_limit` | `fail / model_limit` |
| `qwen3.5:4b` | `indeterminate / model_limit` | `pass / completed` | `pass / completed` | `fail / model_limit` | `fail / completed` |

按任务汇总，Terminal 的通过率最高，为 3/5（60%）；Weather 和 Calculator 均为 2/5（40%）；Reminders 与 WeChat 均为 1/5（20%）。两个个人写入任务的通过率最低，但本批次样本量只有每题 5 次，不能据此断言写入任务在统计意义上必然更难。

## 十、指标对比图与解读

以下图表均比较同一批次的 5 个模型，因此统一使用从零开始的柱状图。颜色只用于区分模型，精确值以柱顶标签和总体结果表为准。

### 总分

总分同时包含截图效果和效率。`qwen3.8:latest` 以 69.90 排名第一，`z-ai/glm-5.3-flash` 以 64.56 排名第二；由于 `indeterminate` 仍可获得部分效果分，总分排名不能替代严格成功率。

![模型总分对比](baseline-desktop-evaluation-report-charts/overall-score.png)

### 成功率

成功率只统计 5 个已测量任务中的 `pass`。`qwen3.8:latest` 为 4/5，`z-ai/glm-5.3-flash` 为 3/5，`qwen3.5:4b` 为 2/5；其余两个模型为 0/5。

![模型成功率对比](baseline-desktop-evaluation-report-charts/success-rate.png)

### 平均步长

平均步长统计动作工具调用数量，越低只表示执行动作更少，不代表任务一定完成。`z-ai/glm-5.3-flash` 平均 4.60 步最低，`qwen3.5:9b` 平均 13.60 步最高。

![模型平均步长对比](baseline-desktop-evaluation-report-charts/average-actions.png)

### 平均执行时长

平均执行时长仅反映 Agent 执行阶段。`qwen3.5:4b` 最短，为 28.81 秒；`qwen3.8:latest` 最长，为 178.22 秒。低耗时可能来自快速完成，也可能来自提前失败，因此必须结合成功率和终止状态解释。

![模型平均执行时长对比](baseline-desktop-evaluation-report-charts/average-execution-duration.png)

### 平均总时长

平均总时长从单题开始计到独立评审结束，包含 60 秒评审冷却、截图评审和可能的中断收尾，不是纯执行耗时。`qwen3.5:4b` 平均 92.33 秒最低，`qwen3.8:latest` 平均 244.21 秒最高。

![模型平均总时长对比](baseline-desktop-evaluation-report-charts/average-total-duration.png)

### 工具调用总数

工具调用总数覆盖 5 项任务。`z-ai/glm-5.3-flash` 共 29 次最低，`qwen3.5:9b` 共 83 次最高；调用更少只有在任务通过时才代表更高效率。

![模型工具调用总数对比](baseline-desktop-evaluation-report-charts/total-tool-calls.png)

### 工具失败次数

`z-ai/glm-5.3-flash` 没有记录工具失败，`qwen3.8:latest` 记录 2 次；`qwen3.5:9b` 的 14 次工具失败为本批次最高。该指标描述工具层可靠性，但不区分失败来自定位、参数、应用状态还是其他原因。

![模型工具失败次数对比](baseline-desktop-evaluation-report-charts/total-tool-failures.png)

### 执行 Token 总数

执行 Token 不包含独立评审 Token。`z-ai/glm-5.3-flash` 为 160107，最低；`qwen3.5:9b` 为 475644，最高。不同模型和 provider 的分词方式可能不同，因此该指标适合观察本次运行成本，不宜直接视为完全同尺度的模型效率度量。

![模型执行 Token 总数对比](baseline-desktop-evaluation-report-charts/execution-tokens.png)

## 十一、证据、产物与复现方式

每次完整运行只生成一份 JSON，保存在 `artifacts/evaluations/baseline-desktop/`。JSON 内含运行清单、任务摘要和逐题结果；逐题结果会引用终态截图与 JSONL 运行日志。报告命令读取 1–5 份运行 JSON，在 `artifacts/evaluations/baseline-desktop-reports/` 下生成新的时间戳目录，其中包含 `report.md` 和 8 张 `charts/*.png`，不会覆盖旧报告。

运行单个模型：

```bash
export MAX_QINIU_KEY="<评审服务密钥>"
max --baseline
```

CLI 会在每道题前暂停，等待用户把目标窗口前置并确认。更换执行 provider 和模型后重复运行，可以得到其他模型的 JSON。多轮运行可使用 `max --baseline --baseline-runs 3`，但每轮都会再次创建提醒和发送微信消息。

使用本报告的 5 份记录重新生成对比报告：

```bash
max --baseline -report \
  artifacts/evaluations/baseline-desktop/20260831-132810.json \
  artifacts/evaluations/baseline-desktop/20260831-135339.json \
  artifacts/evaluations/baseline-desktop/20260831-141441.json \
  artifacts/evaluations/baseline-desktop/20260831-150012.json \
  artifacts/evaluations/baseline-desktop/20260831-151441.json
```

本报告使用的原始运行记录为：

1. `20260831-132810.json`：`z-ai/glm-5.3-flash`
2. `20260831-135339.json`：`qwen3-vl:8b`
3. `20260831-141441.json`：`qwen3.8:latest`
4. `20260831-150012.json`：`qwen3.5:9b`
5. `20260831-151441.json`：`qwen3.5:4b`

## 十二、限制与不确定性

- 每个模型只运行 1 轮、每轮只有 5 项任务，任何一个任务的结果都会使模型成功率变化 20 个百分点，样本不足以支持统计显著性结论。
- 五次运行虽然使用相同任务文件和平台，但真实桌面的窗口位置、应用状态、网络响应、天气搜索结果和运行时负载没有完全冻结。
- 独立评审固定使用一个视觉语言模型，没有进行人工双盲复核或多评审模型一致性校准；其中 `z-ai/glm-5.3-flash` 同时作为第一组的执行模型和所有组的评审模型，但评审阶段只接收终态截图和 rubric，不接收执行过程或模型自述。
- Qiniu 与 Ollama 的推理运行时不同，模型规模、量化方式和 Token 统计口径也可能不同，因此耗时与 Token 差异不能完全归因于模型架构。
- 总分中的 300 秒、10 个动作、15 次工具调用和 100000 Token 是版本化参考值，不是通过真实用户研究得到的自然阈值。总分适合本版本内比较，不应跨评分版本直接对比。
- 当前验收只检查单张终态截图，不验证完整轨迹中的误点击、绕路、潜在副作用或中间状态。天气题的 rubric 也没有限定具体日期和必需字段。
- Reminders 和 WeChat 是真实个人写入任务，系统不自动清理其副作用；实际复现前必须再次获得用户授权。

## 十三、建议的后续评测

1. 每个模型至少重复 3–5 轮，并报告均值、标准差和任务级置信区间，降低单次桌面状态造成的波动。
2. 固定窗口布局、显示缩放、应用初始状态和网络条件，并在每轮前保存环境检查清单。
3. 抽样加入人工复核或第二个评审模型，测量 `pass`、`fail`、`indeterminate` 的一致性。
4. 在任务级成功率之外补充元素识别、定位命中、动作参数正确率、无效动作和错误恢复等原子指标，用于解释失败原因。
5. 如果要比较本地模型与远程模型的纯模型能力，应尽量统一量化方式、上下文、推理参数和运行硬件，并单独报告 provider/runtime 开销。

## 十四、最终结论

在当前 `baseline-desktop-v1`、单轮真实 macOS 环境和固定截图评审条件下，`qwen3.8:latest` 是本批次表现最好的执行模型，成功率为 80.0%，平均总分为 69.90；`z-ai/glm-5.3-flash` 次之，成功率为 60.0%。本批次证明了该评测链路能够执行真实桌面任务、保存终态截图、进行独立验收并汇总效果与效率指标，但由于样本量小、桌面环境未完全冻结且只有单一评审模型，结论应视为当前配置下的工程基线，而不是模型通用 GUI 能力的最终排名。
