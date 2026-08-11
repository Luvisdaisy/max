## MODIFIED Requirements

### Requirement: 聊天内受限工具循环
Textual 聊天 SHALL 将每条普通用户消息交给完整 `AgentRuntime`。运行时 SHALL 重复请求模型返回最终文本或一个结构化工具调用：最终文本结束任务；工具调用经注册表、预算和权限策略处理后，其净化结果加入同一任务消息上下文并进入下一模型轮次。有副作用工具 MUST 额外经过 Guard、动作后观察和验证。界面 SHALL 通过现有事件接收器显示不含参数与回执数据的阶段通知、工具名称、执行状态、耗时摘要以及最终文本，但 MUST NOT 显示或持久化原始截图、完整 OCR 文本、工具参数、工具原始数据、模型思维过程或输入文本。

#### Scenario: 解释当前桌面
- **WHEN** 开发者在聊天中请求描述当前桌面，且模型先后选择有效的 `observe_screen` 和 OCR 工具调用
- **THEN** 系统逐轮执行工具、显示净化执行状态、把结果交回同一任务模型，并在模型返回最终文本后显示解释

#### Scenario: 普通聊天无需工具
- **WHEN** 模型首轮判断用户消息不需要工具并返回最终文本
- **THEN** 系统不获取桌面控制锁、不调用 `observe_screen` 或其他工具、不显示虚构的工具活动、不附加屏幕理解，并显示运行时返回的 `response_text`

#### Scenario: 工具选择失败
- **WHEN** 模型返回无效或未授权的工具选择、工具参数校验失败，或者获准工具执行失败
- **THEN** AgentRuntime 将仅含工具名、稳定错误分类和安全摘要的工具结果加入任务消息上下文，并在剩余预算内请求下一模型响应或受控失败

#### Scenario: 问候触发了不适用工具
- **WHEN** 用户发送普通问候且模型错误选择了需要当前上下文无法提供之输入的工具
- **THEN** AgentRuntime 将失败作为净化工具结果回填并允许模型返回问候文本，而不是以未处理的 `tool_failed` 异常结束本轮对话

#### Scenario: 工具失败后的最终生成也失败
- **WHEN** 系统已将净化的工具失败结果交给模型，但本地模型仍无法生成合法工具调用或最终文本
- **THEN** 界面显示不含敏感回执的明确本地运行时错误、恢复输入并保持会话可用

### Requirement: Default chat-first terminal interface
The application SHALL provide a keyboard-first Textual terminal interface as its only interactive experience. The transcript SHALL visually distinguish user messages, MAX Markdown responses, system or command results, sanitized AgentRuntime model-turn and tool activity, and errors while keeping chat history, the composer, the selected model, the local runtime state, and the controlled-desktop safety boundary discoverable. `max-agent` and `max-agent --chat` SHALL start the same Textual interface. Ordinary text SHALL be sent to AgentRuntime, which uses the selected local model in a bounded text-or-tool loop and may return a direct conversational response or execute a controlled desktop task. This change MUST NOT require changes to the existing Textual layout or widgets.

#### Scenario: Start the default interface
- **WHEN** a developer starts `max-agent` in an interactive terminal
- **THEN** the application opens the existing Textual chat interface, focuses the composer, identifies the selected local model and accepts ordinary text and supported slash commands

#### Scenario: Start the explicit chat interface
- **WHEN** a developer runs `max-agent --chat`
- **THEN** the application starts the same Textual chat interface used by the default entry point, with AgentRuntime available without an additional desktop-control flag

#### Scenario: Render a development-oriented response
- **WHEN** AgentRuntime returns `response_text` containing headings, lists, inline code or fenced code blocks
- **THEN** the interface renders the response as readable Markdown within the existing visually distinct MAX message region

#### Scenario: Send chat text before an AI backend exists
- **WHEN** a developer submits ordinary text and the selected local runtime cannot generate a valid Agent action or response
- **THEN** the interface preserves the user message, displays a visually distinct local runtime failure and restores the composer for another action

### Requirement: Shared interactive command dispatch
The application SHALL continue to support `/doctor`, `/help`, `/clear`, `/status` and `/quit` in the Textual interface. Typing `/` in an otherwise empty composer SHALL show the existing keyboard-navigable, filterable command list without starting AgentRuntime. `/doctor` SHALL run the existing no-input diagnostic operation; `/help` SHALL show available commands and shortcuts; `/clear` SHALL clear the visible transcript, local model conversation history and any `WAITING_USER` Agent task while preserving the selected model; `/status` SHALL report the selected model, runtime state and active controlled-desktop safety boundary; `/quit` SHALL exit cleanly after cancelling and cleaning up any running or suspended task.

#### Scenario: Discover supported commands
- **WHEN** a developer types `/` in an empty composer and continues typing a command prefix
- **THEN** the interface displays and filters matching supported commands, allows keyboard selection and does not start model inference or AgentRuntime

#### Scenario: Run diagnostics from an interactive frontend
- **WHEN** a developer enters `/doctor`
- **THEN** the interface displays the diagnostic outcome in a command-result region and preserves the session for further input

#### Scenario: Show command help
- **WHEN** a developer enters `/help`
- **THEN** the interface displays supported slash commands and composer shortcuts without starting model inference or AgentRuntime

#### Scenario: Clear the current conversation
- **WHEN** a developer enters `/clear`
- **THEN** the interface clears the visible transcript, local conversation history and suspended Agent task, retains the selected model and presents a fresh ready composer

#### Scenario: Inspect session status
- **WHEN** a developer enters `/status`
- **THEN** the interface reports the selected model, local runtime state and actual controlled-desktop safety boundary without starting model inference or AgentRuntime

#### Scenario: Exit from an interactive frontend
- **WHEN** a developer enters `/quit`
- **THEN** the interface cancels and cleans up any active or suspended task, then exits cleanly without starting new model inference or desktop control

#### Scenario: Unsupported slash command
- **WHEN** a developer enters an unsupported slash command
- **THEN** the interface reports that the command is unsupported, suggests `/help` and remains available for input

### Requirement: 单活动请求与可恢复运行状态
Textual 聊天界面 SHALL 在任一时刻只允许一个普通消息对应的 AgentRuntime 调用执行。请求执行期间，界面 MUST 阻止重复提交并持续显示当前阶段与已用时间；调用返回 `SUCCEEDED`、`WAITING_USER`、`FAILED` 或 `ABORTED` 后 MUST 停止忙碌指示、恢复编辑区和键盘焦点，并保持既有会话内容可读。`WAITING_USER` 的下一条普通消息 SHALL 恢复同一挂起任务，但仍作为一个新的单活动调用经过现有门禁。

#### Scenario: 普通请求开始运行
- **WHEN** 开发者提交一条普通聊天消息
- **THEN** 界面立即显示该用户消息、锁定新的提交并显示 AgentRuntime 当前模型轮次或工具阶段与递增的已用时间

#### Scenario: 忙碌期间尝试重复提交
- **WHEN** 一个 AgentRuntime 调用仍在执行且开发者触发发送操作
- **THEN** 界面不启动第二个调用、不取消现有调用，并明确提示当前请求仍在运行

#### Scenario: 请求完成后恢复
- **WHEN** AgentRuntime 返回最终答复、用户问题或本地错误
- **THEN** 界面呈现对应结果、结束忙碌状态、重新允许输入并将焦点恢复到编辑区

### Requirement: 交互式模型选择命令
Textual 聊天界面 SHALL 支持 `/model` 和 `/model <模型目录>`。无参数命令 MUST 显示可选本地模型及当前选择；带参数命令 MUST 请求切换到指定模型，并将成功或失败结果显示在当前会话中，不启动普通 AgentRuntime 调用。成功切换模型 MUST 清除旧模型的对话历史、规划会话和 `WAITING_USER` 任务，使后续普通文本创建使用新模型的新任务。

#### Scenario: 查看模型清单
- **WHEN** 开发者在 Textual 会话输入 `/model`
- **THEN** 界面显示可选模型、当前模型和选择用法，并保持输入可用

#### Scenario: 会话中切换模型
- **WHEN** 开发者在已有聊天记录或挂起任务的会话中输入 `/model <模型目录>` 且选择成功
- **THEN** 界面确认切换，清除旧规划会话和挂起任务，后续普通文本使用新模型，且不会将先前模型的对话或 Agent 状态发送给新模型

#### Scenario: 模型命令参数无效
- **WHEN** 开发者输入不存在的模型名称或不合法的 `/model` 参数
- **THEN** 界面显示明确错误并保持当前模型选择、规划状态与会话可用
