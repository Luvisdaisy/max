## MODIFIED Requirements

### Requirement: 聊天内受限工具循环
Textual 聊天 SHALL 允许模型在处理一条普通用户消息时选择至多一次已注册的只读工具。工具成功回执中的内存观察 MUST 回传同一模型继续推理；界面 SHALL 显示不含参数与回执数据的工具名称、执行状态和耗时摘要以及最终文本回复，但 MUST NOT 显示或持久化原始截图、工具参数、工具原始数据或模型工具选择提示。

#### Scenario: 解释当前桌面
- **WHEN** 开发者在聊天中请求描述当前桌面，且模型选择有效的 `observe_screen` 调用
- **THEN** 系统获取内存截图、显示 `observe_screen` 的净化执行状态、由模型继续分析并在当前会话显示最终解释

#### Scenario: 普通聊天无需工具
- **WHEN** 模型判断用户消息不需要已注册工具
- **THEN** 系统不调用工具、不显示虚构的工具活动，并按现有本地聊天流程生成回复

#### Scenario: 工具选择失败
- **WHEN** 模型返回无效或未授权的工具选择，工具参数校验失败，或者获准的只读工具执行失败
- **THEN** 系统将仅含工具名、稳定错误分类和安全摘要的失败观察交回模型，不重试或改调其他工具，并要求模型结合原始用户消息生成最终回答

#### Scenario: 问候触发了不适用工具
- **WHEN** 用户发送普通问候且模型错误选择了需要当前上下文无法提供之输入的工具
- **THEN** Agent 在最终回复中理解该工具失败并继续回应问候，而不是以 `tool_failed` 错误结束本轮对话

#### Scenario: 工具失败后的最终生成也失败
- **WHEN** 系统已将净化的工具失败观察交回模型，但本地模型无法生成最终回复
- **THEN** 界面显示不含敏感回执的明确本地运行时错误、恢复输入并保持会话可用

### Requirement: Default chat-first terminal interface
The application SHALL provide a keyboard-first Textual terminal interface as its only interactive experience. The transcript SHALL visually distinguish user messages, MAX Markdown responses, system or command results, sanitized tool activity, and errors while keeping chat history, the composer, the selected model, the local runtime state, and the read-only safety boundary discoverable. `max-agent` and `max-agent --chat` SHALL start the same Textual interface. Ordinary text SHALL be sent to the local LLM runtime rather than receiving a fabricated unconfigured-backend message.

#### Scenario: Start the default interface
- **WHEN** a developer starts `max-agent` in an interactive terminal
- **THEN** the application opens the Textual chat interface, focuses the composer, identifies the selected local model and accepts ordinary text and supported slash commands

#### Scenario: Start the explicit chat interface
- **WHEN** a developer runs `max-agent --chat`
- **THEN** the application starts the same Textual chat interface used by the default entry point

#### Scenario: Render a development-oriented response
- **WHEN** the local model returns text containing headings, lists, inline code or fenced code blocks
- **THEN** the interface renders the response as readable Markdown within a visually distinct MAX message region

#### Scenario: Send chat text before an AI backend exists
- **WHEN** a developer submits ordinary text and the selected local runtime cannot generate a response
- **THEN** the interface preserves the user message, displays a visually distinct local runtime failure and restores the composer for another action

### Requirement: Shared interactive command dispatch
The application SHALL support `/doctor`, `/help`, `/clear`, `/status` and `/quit` in the Textual interface. Typing `/` in an otherwise empty composer SHALL show a keyboard-navigable, filterable list of supported commands without starting local inference. `/doctor` SHALL run the existing no-input diagnostic operation; `/help` SHALL show available commands and shortcuts; `/clear` SHALL clear the visible transcript and local conversation history while preserving the selected model; `/status` SHALL report the selected model, runtime state and active read-only boundary; `/quit` SHALL exit cleanly.

#### Scenario: Discover supported commands
- **WHEN** a developer types `/` in an empty composer and continues typing a command prefix
- **THEN** the interface displays and filters matching supported commands, allows keyboard selection and does not start model inference

#### Scenario: Run diagnostics from an interactive frontend
- **WHEN** a developer enters `/doctor`
- **THEN** the interface displays the diagnostic outcome in a command-result region and preserves the session for further input

#### Scenario: Show command help
- **WHEN** a developer enters `/help`
- **THEN** the interface displays supported slash commands and composer shortcuts without starting model inference

#### Scenario: Clear the current conversation
- **WHEN** a developer enters `/clear`
- **THEN** the interface clears the visible transcript and local conversation history, retains the selected model and presents a fresh ready composer

#### Scenario: Inspect session status
- **WHEN** a developer enters `/status`
- **THEN** the interface reports the selected model, local runtime state and read-only tool boundary without starting model inference

#### Scenario: Exit from an interactive frontend
- **WHEN** a developer enters `/quit`
- **THEN** the interface exits cleanly without starting new model inference or desktop control

#### Scenario: Unsupported slash command
- **WHEN** a developer enters an unsupported slash command
- **THEN** the interface reports that the command is unsupported, suggests `/help` and remains available for input

## ADDED Requirements

### Requirement: 多行键盘输入与本地历史
Textual 聊天界面 SHALL 提供支持多行文本的编辑区。`Enter` MUST 提交非空内容，`Shift+Enter` MUST 插入换行；空白内容 MUST NOT 创建消息或启动命令。界面 SHALL 允许开发者使用键盘访问本次进程中的已提交输入，输入历史 MUST NOT 跨进程持久化。

#### Scenario: 提交多行任务
- **WHEN** 开发者使用 `Shift+Enter` 编写多行内容后按 `Enter`
- **THEN** 界面将完整多行内容作为一条用户消息提交，并清空编辑区

#### Scenario: 忽略空白输入
- **WHEN** 编辑区仅包含空白字符且开发者按 `Enter`
- **THEN** 界面不追加消息、不改变运行状态且保持编辑区可用

#### Scenario: 浏览本地输入历史
- **WHEN** 编辑区没有未提交修改且开发者触发上一条或下一条历史输入操作
- **THEN** 界面在本次进程已提交的输入之间导航，不读取或写入持久化会话数据

### Requirement: 单活动请求与可恢复运行状态
Textual 聊天界面 SHALL 在任一时刻只允许一个普通聊天请求执行。请求执行期间，界面 MUST 阻止重复提交并持续显示当前阶段与已用时间；请求成功或失败后 MUST 停止忙碌指示、恢复编辑区和键盘焦点，并保持既有会话内容可读。

#### Scenario: 普通请求开始运行
- **WHEN** 开发者提交一条普通聊天消息
- **THEN** 界面立即显示该用户消息、锁定新的提交并显示本地模型加载或生成阶段与递增的已用时间

#### Scenario: 忙碌期间尝试重复提交
- **WHEN** 一个普通聊天请求仍在执行且开发者触发发送操作
- **THEN** 界面不启动第二个请求、不取消现有请求，并明确提示当前请求仍在运行

#### Scenario: 请求完成后恢复
- **WHEN** 普通聊天请求返回最终回复或本地错误
- **THEN** 界面呈现对应结果、结束忙碌状态、重新允许输入并将焦点恢复到编辑区

### Requirement: 可预测的会话滚动与窄终端布局
Textual 聊天界面 SHALL 在终端尺寸变化时保持内容可读且不要求水平滚动。新内容到达时，若开发者位于记录底部，界面 MUST 跟随最新内容；若开发者正在回看较早内容，界面 MUST 保持当前位置并提示存在新内容，直至开发者主动返回底部。

#### Scenario: 跟随最新回复
- **WHEN** 新会话内容到达且开发者当前位于记录底部
- **THEN** 界面自动滚动以展示最新内容

#### Scenario: 回看历史时收到回复
- **WHEN** 开发者已向上滚动查看较早内容且新会话内容到达
- **THEN** 界面保留当前阅读位置并显示可通过键盘返回最新内容的提示

#### Scenario: 缩小终端宽度
- **WHEN** 终端被缩小到无法容纳完整宽屏状态栏的宽度
- **THEN** 界面换行会话内容并压缩或隐藏次要状态信息，同时保留编辑区、运行状态和主要消息类型的可辨识性
