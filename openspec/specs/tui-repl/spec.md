# tui-repl Specification

## Purpose

Textual REPL：提示符、历史、流式 token、斜杠命令、非阻塞界面。

## Requirements

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

TUI SHALL 在 token 到达时渲染，并 MUST 追加到记录区当前助手消息。

#### Scenario: token 级展示

- **WHEN** 推理客户端产出一个 token
- **THEN** 当前助手消息立即更新，不等待完整完成

### Requirement: 斜杠命令

TUI SHALL 至少支持 `/new`、`/sessions`、`/attach`、`/model`、`/interrupt`、`/quit`。未知命令 MUST 在记录区显示错误，且 MUST NOT 启动 Agent 运行。

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
