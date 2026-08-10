# chat-console-ui Specification

## Purpose

提供唯一的 Textual 本地聊天入口，使开发者能够在同一交互会话中使用本地模型、诊断运行环境并安全退出。

## Requirements

### Requirement: 聊天内受限工具循环
Textual 聊天 SHALL 允许模型在处理一条普通用户消息时选择至多一次已注册的只读工具。工具成功回执中的内存观察 MUST 回传同一模型继续推理，界面 MUST 仅显示最终文本回复，不显示或持久化原始截图与工具原始数据。

#### Scenario: 解释当前桌面
- **WHEN** 开发者在聊天中请求描述当前桌面，且模型选择有效的 `observe_screen` 调用
- **THEN** 系统获取内存截图、由模型继续分析并在当前会话显示最终解释

#### Scenario: 普通聊天无需工具
- **WHEN** 模型判断用户消息不需要已注册工具
- **THEN** 系统不调用工具并按现有本地聊天流程生成回复

#### Scenario: 工具选择失败
- **WHEN** 模型返回无效、未授权或失败的工具调用
- **THEN** 界面显示明确的本地错误且保持会话可用，不发送桌面输入或网络请求

### Requirement: Default chat-first terminal interface
The application SHALL provide a Textual terminal interface as its only interactive experience, with visible chat history, input, loading and error status, and a graceful exit action. `max-agent` and `max-agent --chat` SHALL start the same Textual interface. Ordinary text SHALL be sent to the local LLM runtime rather than receiving a fabricated unconfigured-backend message.

#### Scenario: Start the default interface
- **WHEN** a developer starts `max-agent` in an interactive terminal
- **THEN** the application opens the Textual chat interface and accepts ordinary text and supported slash commands

#### Scenario: Start the explicit chat interface
- **WHEN** a developer runs `max-agent --chat`
- **THEN** the application starts the same Textual chat interface used by the default entry point

#### Scenario: Send chat text before an AI backend exists
- **WHEN** a developer submits ordinary text
- **THEN** the interface displays the user message, the local runtime state, and either the generated local response or a clear local runtime failure

### Requirement: Shared interactive command dispatch
The application SHALL support `/doctor` and `/quit` in the Textual interface. `/doctor` SHALL run the existing no-input diagnostic operation and render its outcome in the session; `/quit` SHALL exit cleanly without starting new inference or desktop control.

#### Scenario: Run diagnostics from an interactive frontend
- **WHEN** a developer enters `/doctor`
- **THEN** the interface displays the diagnostic outcome and preserves the session for further input

#### Scenario: Exit from an interactive frontend
- **WHEN** a developer enters `/quit`
- **THEN** the interface exits cleanly without starting new model inference or desktop control

#### Scenario: Unsupported slash command
- **WHEN** a developer enters an unsupported slash command
- **THEN** the interface reports that the command is unsupported and remains available for input

### Requirement: 交互式模型选择命令
Textual 聊天界面 SHALL 支持 `/model` 和 `/model <模型目录>`。无参数命令 MUST 显示可选本地模型及当前选择；带参数命令 MUST 请求切换到指定模型，并将成功或失败结果显示在当前会话中，不启动普通聊天推理。

#### Scenario: 查看模型清单
- **WHEN** 开发者在 Textual 会话输入 `/model`
- **THEN** 界面显示可选模型、当前模型和选择用法，并保持输入可用

#### Scenario: 会话中切换模型
- **WHEN** 开发者在已有聊天记录的会话中输入 `/model <模型目录>` 且选择成功
- **THEN** 界面确认切换，后续普通文本使用新模型，且不会将先前模型的对话历史发送给新模型

#### Scenario: 模型命令参数无效
- **WHEN** 开发者输入不存在的模型名称或不合法的 `/model` 参数
- **THEN** 界面显示明确错误并保持当前模型选择与会话可用

### Requirement: Restricted startup surface
The application SHALL expose only `max-agent` and `max-agent --chat` as supported public startup forms. It MUST NOT expose `doctor`, `download-model`, `validate-model`, `benchmark`, `--doctor`, `--fallback`, or `--textual` as public command-line operations. Removing those public operations MUST NOT require deletion of their underlying local model-management or benchmark implementation modules.

#### Scenario: Unsupported legacy CLI operation
- **WHEN** a developer invokes a removed command or option
- **THEN** the command exits with usage feedback and does not start a different frontend or trigger model, desktop, or download work
