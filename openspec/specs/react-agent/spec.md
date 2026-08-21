# react-agent Specification

## Purpose

LangGraph ReAct 循环、状态、JSON 检查点、中断恢复。

## Requirements

### Requirement: ReAct 状态机

Agent SHALL 用 LangGraph StateGraph 实现 `think`、`act`、`observe` 节点。一个回合 MUST 从 `think` 开始。若模型返回工具调用，图 MUST 先跑 `act` 再 `observe`，然后回到 `think`。若模型不再返回工具调用，图 MUST 以 `done` 结束。

#### Scenario: 纯文本完成

- **WHEN** 模型返回最终助手消息且无工具调用
- **THEN** 图状态为 `done`，且不调用任何工具

#### Scenario: 一次工具循环

- **WHEN** 模型返回工具调用且工具成功
- **THEN** 图执行 `act` 再 `observe`，追加工具结果，并再次调用 `think`

### Requirement: 迭代上限

Agent MUST 在单次用户回合中，于配置的最大 Think/Act/Observe 循环次数后停止。触达上限时，状态 MUST 为 `error`，记录 MUST 包含迭代上限说明。未设置 `MAX_GUI_MAX_ITERATIONS` 时，`max_iterations` MUST 默认为 20。

#### Scenario: 达到最大迭代

- **WHEN** 模型在 `max_iterations` 轮之后仍继续请求工具
- **THEN** Agent 不再分发下一个工具，并向用户报告已达迭代上限

#### Scenario: 未配置环境变量

- **WHEN** 进程未设置 `MAX_GUI_MAX_ITERATIONS`
- **THEN** 配置中的最大循环次数为 20

### Requirement: 中断与恢复

Agent MUST 接受来自 TUI 的中断。中断状态 MUST 写入该会话 JSON 中的检查点。恢复同一会话 MUST 从最近检查点恢复图状态，而不是从头重跑该回合，除非用户开始新回合。不得使用 SQLite 保存检查点。

#### Scenario: 运行中中断

- **WHEN** 用户在 `think` 或 `act` 期间中断
- **THEN** 状态变为 `interrupted`，检查点写入该会话 JSON

#### Scenario: 中断后恢复

- **WHEN** 用户在中断后继续同一会话
- **THEN** Agent 加载最近检查点并从该节点继续

### Requirement: 上下文包含工具结果

`observe` 之后，下一次 `think` 调用 MUST 包含此前的用户/助手消息以及本回合最新工具结果。

#### Scenario: 模型能看到工具输出

- **WHEN** `read_file` 返回文件内容
- **THEN** 随后的 `think` 模型请求把这些内容作为 tool 消息带上

### Requirement: GUI 系统契约注入

每次 `think` 发给模型的消息列表 MUST 以一条中文 `role=system` 消息开头。该消息 MUST 要求：桌面任务一律用键鼠完成；每一次键鼠动作都必须截图核验；还没有画面时先 `screenshot`；要点、拖、输入前先 `mouse_move`，根据回注图上的光标判断位置，对了再调用不带坐标的 `mouse_click` 或拖拽/键盘；看到回注图后 MUST 先判断红十字落在哪个控件上，与目标不一致则再 `mouse_move`，MUST NOT 在未看图时点击；坐标只用最近一帧视图像素或 `ocr_locate` 的 `target_id`，且视图像素必须落在该帧 `view_width`×`view_height` 内；不要用逻辑分辨率、屏幕百分比、归一化坐标，也不要把工具摘要里的逻辑坐标再当输入；看不清字再 OCR；破坏性桌面动作一次一个；动作后根据新画面判断是否进入下一子任务；首轮尽量输出编号子任务。该消息 MUST 写明当前操作系统的中文名称；当主机为 macOS 时 MUST 写明不是 Windows，快捷键用 `command` 而不是 `windows`。若当前会话已有视图帧，该消息 MUST 包含该帧的 `view_width` 与 `view_height`。该 `system` 消息 MUST NOT 写入会话 JSON，MUST NOT 作为 TUI 记录区条目出现。

#### Scenario: think 请求带 system

- **WHEN** Agent 进入 `think` 并调用推理客户端
- **THEN** 请求的 `messages` 第一条 `role` 为 `system`，正文含「先截图」、先移鼠看光标、视图像素约定与视图宽高边界

#### Scenario: 会话不保存 system

- **WHEN** 一回合结束并落盘
- **THEN** 该会话 JSON 的 `messages` 中没有 `role` 为 `system` 的条目

#### Scenario: macOS 上标明不是 Windows

- **WHEN** 主机为 macOS，Agent 进入 `think`
- **THEN** 系统消息含「macOS」，且含「不是 Windows」或等价说明，以及使用 `command` 而非 `windows`

#### Scenario: 有视图帧时写出宽高

- **WHEN** 当前会话视图为 1536×864，Agent 进入 `think`
- **THEN** 系统消息含 `1536` 与 `864`

### Requirement: think 推理异常结束为 error

`think` 调用推理客户端失败时 MUST 将图状态设为 `error`，写入人类可读错误，MUST NOT 把未捕获异常甩出图外导致会话仍为上一回合的 `done`。

#### Scenario: 流式 HTTP 错误变成会话错误

- **WHEN** `/chat/completions` 返回非 2xx
- **THEN** `AgentRunner.run` 返回的状态 `status` 为 `error`，且该状态被写入当前会话

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

### Requirement: 图执行期间发出进度

`AgentRunner` 在每个节点进入时 MUST 回调当前状态名（`thinking` / `acting` / `observing`）。流式思考与正文 MUST 在 `think` 等待模型期间分别回调。一条助手消息在 `think` 拼装完成后 MUST 立即回调 `on_message`。`act` 中每完成一次 `registry.invoke` MUST 立即回调该条 tool 消息，MUST NOT 等到本节点全部工具结束。

#### Scenario: 状态随节点变化

- **WHEN** 模型返回工具调用并进入 `act`
- **THEN** 在工具执行前调用方已收到状态 `acting`

#### Scenario: 单次工具完成后即可见

- **WHEN** 一次 `think` 请求了两个工具且 `act` 顺序执行
- **THEN** 第一个工具返回后，调用方在第二个工具返回前已收到该 tool 的 `on_message`

### Requirement: think 与 act 增量持久化

`think` 产生助手消息后 MUST 立刻写入当前会话 JSON。`act` 每完成一个工具 MUST 立刻将该 tool 消息写入当前会话 JSON。图正常结束时 MUST 更新 `status` 与检查点，MUST NOT 把已写入的同一条消息再追加一次。

#### Scenario: 工具循环中途会话已有助手消息

- **WHEN** 模型返回带工具调用的助手消息且 `act` 尚未全部完成
- **THEN** 该会话 JSON 已包含这条助手消息

#### Scenario: 结束不重复追加

- **WHEN** 一回合含一次工具循环后以无工具调用结束
- **THEN** 会话 JSON 中该助手与 tool 消息各出现一次
