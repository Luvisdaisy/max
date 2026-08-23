# tui-repl Specification

## Purpose

Textual REPL：提示符、历史、流式 token、斜杠命令、非阻塞界面。

## Requirements

### Requirement: 默认展示独立运行监控面板

TUI MUST 在会话记录区之外默认展示独立运行监控面板。面板 MUST 显示当前运行编号摘要、状态、当前轮次与上限、当前子任务、活动模型或工具、累计耗时、模型与工具累计耗时、工具成功/失败数和最近运行事件；没有活动运行时 MUST 显示就绪或最近终态。运行监控内容 MUST NOT 作为用户、助手或工具消息写入会话记录区。

#### Scenario: 启动后面板默认可见

- **WHEN** 用户启动 Textual REPL 且尚未提交新任务
- **THEN** 独立运行监控面板已经可见并显示就绪状态

#### Scenario: 工具执行时实时更新

- **WHEN** Agent 发出 `tool.started` 事件
- **THEN** 面板在工具返回前显示当前工具名和执行中状态，会话记录区不新增调试事件行

#### Scenario: 运行完成后保留摘要

- **WHEN** Agent 发出运行终态事件
- **THEN** 面板显示该运行的最终状态、总耗时、调用统计和最近事件

### Requirement: 监控面板展示 token 用量

独立运行监控面板 MUST 展示本次运行已累计的输入、输出与合计 token。有已知累计时 MUST 使用中文「用量：输入 N / 输出 M / 合计 T」形式。没有任何已知用量时 MUST 显示「用量：未知」，MUST NOT 显示输入 0、输出 0 来表示未知。最近事件中的模型完成摘要 MUST 包含当次输入与输出，或在当次未知时写「用量未知」。用量 MUST NOT 作为用户、助手或工具消息写入会话记录区。

#### Scenario: 模型完成后面板出现累计用量

- **WHEN** Agent 发出带 `prompt_tokens=12`、`completion_tokens=8`、`total_tokens=20` 的 `model.completed`
- **THEN** 监控面板可见「用量：输入 12 / 输出 8 / 合计 20」，会话记录区不新增用量行

#### Scenario: 未知用量不显示零

- **WHEN** 当前运行尚无任何已知 token 用量
- **THEN** 监控面板显示「用量：未知」，且 MUST NOT 以「输入 0 / 输出 0」表示未知

#### Scenario: 最近事件带当次用量

- **WHEN** 一次模型调用完成且当次用量已知
- **THEN** 面板最近事件摘要含该次输入与输出 token 数

### Requirement: 监控面板隐藏大段敏感正文

监控面板 MUST 只显示事件摘要，MUST NOT 展示完整 reasoning、`keyboard_type` 输入正文、OCR 全文、截图字节、API Key、Authorization Header 或 `.env` 内容。面板 MUST NOT 依赖展示 `artifacts/runs/` 绝对路径来表达运行状态。

#### Scenario: 键盘输入事件只显示工具摘要

- **WHEN** 当前事件来自含正文参数的 `keyboard_type`
- **THEN** 面板可显示工具名、字符数、耗时和结果，但不显示输入正文

### Requirement: 日志写入故障在面板中可见

当运行记录器无法创建或追加 JSONL 时，TUI MUST 在独立监控面板显示中文诊断，且界面 MUST 保持可响应。该诊断 MUST 与 Agent 业务终态分开表达，MUST NOT 把成功完成的任务显示为工具失败。

#### Scenario: 运行文件不可写

- **WHEN** 运行记录器通过内存回调报告写入失败
- **THEN** 面板显示“运行日志写入失败”及安全的错误摘要，用户仍可中断或继续使用 TUI

### Requirement: 启动 Textual REPL

用户执行 `max-gui` 或 `max-gui tui` 时，CLI SHALL 启动 Textual TUI。TUI MUST 展示会话记录、多行提示符和状态区。推理或工具运行时，界面 MUST 保持可响应。

#### Scenario: 默认命令打开 REPL

- **WHEN** 用户不带子命令执行 `max-gui`
- **THEN** Textual REPL 启动，焦点在提示符上

#### Scenario: 推理不冻结输入

- **WHEN** 模型流式输出进行中
- **THEN** 用户仍可在提示符中输入并调用 `/interrupt`

### Requirement: 提交文本回合

用户按下配置的发送键时（默认：Enter；Shift+Enter 插入换行），TUI SHALL 把提示符内容作为用户回合提交。空提交 MUST 被忽略。实现 MUST 拦截 TextArea 对 Enter 的默认换行，不能只注册会被吞掉的 Binding。

#### Scenario: 发送文本消息

- **WHEN** 用户输入非空文本并按 Enter
- **THEN** 记录区追加一条用户消息，并开始 Agent 运行

#### Scenario: 忽略空发送

- **WHEN** 提示符为空或仅空白，用户按 Enter
- **THEN** TUI 不启动 Agent 运行

### Requirement: 流式展示助手 token

TUI SHALL 在 token 到达时渲染进行中的助手条目。思考增量与正文增量 MUST 立即可见，不等待该次 `think` 完整完成。该次 `think` 结束后 MUST 将进行中条目写入记录区。

#### Scenario: token 级展示

- **WHEN** 推理客户端产出一个正文 token
- **THEN** 进行中的助手展示立即更新，不等待完整完成

#### Scenario: 思考 token 级展示

- **WHEN** 推理客户端产出一个思考 token
- **THEN** 进行中的助手展示立即更新，且该 token 出现在思考分区

### Requirement: 斜杠命令

TUI SHALL 至少支持 `/new`、`/sessions`、`/attach`、`/interrupt`、`/quit`。未知命令 MUST 在记录区显示错误，且 MUST NOT 启动 Agent 运行。TUI MUST NOT 将 `/model` 列为受支持命令。

#### Scenario: 开始新会话

- **WHEN** 用户提交 `/new`
- **THEN** TUI 创建新的空会话（新的时间戳 JSON）并清空记录区

#### Scenario: 中断一次运行

- **WHEN** Agent 正在运行且用户提交 `/interrupt`
- **THEN** 运行停止，记录区保留已收到的 token，会话标记为 interrupted

#### Scenario: 未知命令

- **WHEN** 用户提交 `/not-a-command`
- **THEN** TUI 显示命令未找到，且不调用模型

### Requirement: 从 REPL 附加图像

TUI SHALL 允许用户通过 `/attach <path>` 附加一张或多张图像（终端支持时也可用文件拖放）。已附加图像 MUST 列在待发送回合中，并在下一次文本回合发出时一并带上。

#### Scenario: 附加本地图像

- **WHEN** 用户执行 `/attach ./photo.png`，文件存在且为支持的图像类型
- **THEN** TUI 在待发送回合上展示该附件

#### Scenario: 拒绝缺失文件

- **WHEN** 用户执行 `/attach ./missing.png` 且文件不存在
- **THEN** TUI 显示错误，且不添加附件

### Requirement: 工具执行不弹确认

TUI MUST NOT 因 Agent 调用 `mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type` 或 `keyboard_press` 而弹出确认对话框。工具结果仍写入记录区。

#### Scenario: 点击不弹框

- **WHEN** Agent 请求 `mouse_click`
- **THEN** 界面不出现「允许执行」对话框，记录区随后可见工具结果

### Requirement: 展示桌面权限错误

当桌面工具返回屏幕录制或辅助功能失败时，TUI MUST 在记录区展示工具给出的中文步骤，且 MUST NOT 崩溃。

#### Scenario: 记录区显示授权步骤

- **WHEN** `screenshot` 因屏幕录制未授权失败
- **THEN** 记录区显示中文授权步骤

### Requirement: 记录区不展示执行元数据

TUI 展示 `role=tool` 的消息时 MUST 使用 `content.text`（可截断），MUST NOT 把 `exec` 对象当作记录区正文。状态区 MUST NOT 展示 `artifacts/runs/` 路径。

#### Scenario: 工具结果只显示摘要文本

- **WHEN** 一条 tool 消息含截图 JSON 摘要与 `exec.duration_ms`
- **THEN** 记录区可见该摘要文本，且 MUST NOT 把 `duration_ms` 作为独立日志行写出

### Requirement: 模型由配置决定而非斜杠命令

TUI MUST NOT 提供 `/model` 命令。当前推理模型 MUST 来自已加载的 `MODEL_NAME`。用户提交 `/model` 或 `/model <名>` 时 MUST 按未知命令处理。

#### Scenario: /model 视为未知

- **WHEN** 用户提交 `/model` 或 `/model qwen3.5-2b`
- **THEN** TUI 在记录区显示命令未找到，且不改变当前推理模型，且不调用模型补全

#### Scenario: 回合开始不指向 runs 文件

- **WHEN** 用户提交一条非空文本并开始 Agent 运行
- **THEN** 状态区文本不含 `artifacts/runs/`

### Requirement: 逐步展示思考、正文与工具

TUI MUST 在思考 token 到达时更新进行中的助手展示（与正文分区，思考带「思考」标识）。一次 `think` 结束后 MUST 把该次思考与正文写入记录区为一条助手消息，并清空进行中区域。工具结果 MUST 在该次 `act` 完成当时写入记录区。同一用户回合内多次 `think` MUST 成为多条助手记录，MUST NOT 拼成一条。状态区 MUST 显示「思考中…」「执行工具…」「观察中…」中与当前节点对应的文案。

#### Scenario: 长思考过程中记录区已有进行中文本

- **WHEN** 推理客户端正在推送思考或正文 token 且本轮 `think` 尚未结束
- **THEN** 进行中区域可见已到达的文本，记录区尚未把本次 think 落成最终助手条目

#### Scenario: 工具结果不等待整回合

- **WHEN** Agent 正在执行第一个工具且后续还有 think
- **THEN** 记录区已出现该工具结果摘要

#### Scenario: 两轮 think 两条助手记录

- **WHEN** 一回合内模型先调工具再给出最终文本
- **THEN** 记录区有两条助手消息，第二条为最终文本

#### Scenario: 状态栏进入执行工具

- **WHEN** Agent 从 `think` 进入 `act`
- **THEN** 状态区文案为「执行工具…」
