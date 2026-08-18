## ADDED Requirements

### Requirement: GUI 系统契约注入

每次 `think` 发给模型的消息列表 MUST 以一条中文 `role=system` 消息开头。该消息 MUST 要求：先调用 `screenshot` 再给出坐标；坐标只用最近一帧视图像素或 `ocr_locate` 的 `target_id`；看不清字再 OCR；破坏性桌面动作一次一个；动作后根据新画面判断是否进入下一子任务；首轮尽量输出编号子任务。该 `system` 消息 MUST NOT 写入会话 JSON，MUST NOT 作为 TUI 记录区条目出现。

#### Scenario: think 请求带 system

- **WHEN** Agent 进入 `think` 并调用推理客户端
- **THEN** 请求的 `messages` 第一条 `role` 为 `system`，正文含「先截图」与视图像素约定

#### Scenario: 会话不保存 system

- **WHEN** 一回合结束并落盘
- **THEN** 该会话 JSON 的 `messages` 中没有 `role` 为 `system` 的条目

### Requirement: 轻量计划状态

`AgentState` MUST 包含 `plan`（字符串列表）与 `current_subtask`（当前子任务文本或空）。旧检查点缺少这两项时 MUST 视为空计划并仍能恢复。图拓扑 MUST 仍为 `think` / `act` / `observe`，不得增加独立 plan 节点。

当助手文本含至少两行「数字 + `.` 或 `)` + 内容」的编号列表时，Agent MUST 用该列表覆盖 `plan`，并将 `current_subtask` 设为第一项。助手文本含「改计划」且带新编号列表时 MUST 同样覆盖并重置到第一项。工具失败时 MUST NOT 改动当前子任务。助手文本含「子任务完成」或「下一子任务」且 `plan` 非空时，Agent MUST 将当前项推进到下一项（已在末项则保持）。解析失败 MUST NOT 中断 ReAct 循环。

#### Scenario: 首轮编号列表写入计划

- **WHEN** 模型返回含「1. 打开计算器」与「2. 输入 1+1」的助手文本
- **THEN** 状态 `plan` 含这两项，`current_subtask` 为「打开计算器」

#### Scenario: 工具失败不推进子任务

- **WHEN** 当前子任务为计划第一项且本次工具调用失败
- **THEN** `current_subtask` 仍为第一项

#### Scenario: 旧检查点缺计划字段

- **WHEN** 中断检查点没有 `plan` 或 `current_subtask`
- **THEN** Agent 仍能从该检查点恢复，计划视为空

### Requirement: 迭代上限默认值

未设置 `MAX_GUI_MAX_ITERATIONS` 时，`max_iterations` MUST 默认为 20。触达上限时的停止行为 MUST 与既有迭代上限要求一致。

#### Scenario: 未配置环境变量

- **WHEN** 进程未设置 `MAX_GUI_MAX_ITERATIONS`
- **THEN** 配置中的最大循环次数为 20
