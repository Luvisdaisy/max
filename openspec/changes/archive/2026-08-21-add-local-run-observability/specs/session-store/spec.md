## MODIFIED Requirements

### Requirement: 工具消息持久化执行元数据

`role` 为 `tool` 的会话消息 MUST 在 `content` 中保存工具名 `name` 与嵌套对象 `exec`。`exec` MUST 至少包含：`iteration`、`subtask`（无计划时为 `null`）、`arguments`（可 JSON 序列化的短对象；过长 MUST 截断）、`duration_ms`、`error`（无错误为 `null`）、`has_image`。MUST NOT 把图像字节或 base64 写入 `exec`。系统 MUST 允许另写 `artifacts/runs/` 运行事件日志；运行事件 MUST 通过 `session_message_index` 关联已存 tool 消息，MUST NOT 重复写入 reasoning 原文或 `keyboard_type` 输入正文。缺少 `exec` 的旧会话 MUST 仍能加载。发给模型时 MUST NOT 把 `exec` 编进请求正文。

#### Scenario: 截图写入 exec 并允许独立事件

- **WHEN** Agent 成功执行一次 `screenshot` 并保存会话
- **THEN** 对应 tool 消息 `content.name` 为 `screenshot`，`content.exec.has_image` 为真，`content.exec.error` 为 `null`，且对应运行日志可通过消息下标引用该 tool 消息

#### Scenario: 工具错误仍写入 exec

- **WHEN** 工具返回错误文本或业务失败
- **THEN** 该 tool 消息 `content.exec.error` 为非空字符串，且会话仍保存该条消息

#### Scenario: 键盘正文沿用现有会话行为

- **WHEN** `keyboard_type` 的模型参数包含输入正文并被写入工具消息
- **THEN** 正文仍按现有截断规则保存在会话 `exec.arguments`，运行 JSONL 不复制该正文

#### Scenario: 旧会话缺 exec

- **WHEN** 已存 tool 消息没有 `exec` 字段
- **THEN** store 成功加载该会话

## ADDED Requirements

### Requirement: checkpoint 持久化当前运行身份

运行中的 Agent checkpoint MUST 保存当前 `run_id`。旧 checkpoint 缺少 `run_id` 时 MUST 仍能加载；只有带 `run_id` 的 `interrupted` checkpoint 才能恢复并继续追加原运行日志。

#### Scenario: 中断后运行身份可恢复

- **WHEN** Agent 以 `interrupted` 结束并保存 checkpoint
- **THEN** checkpoint 含当前 `run_id`，恢复后事件继续写入该运行对应的 JSONL

#### Scenario: 旧 checkpoint 缺少运行身份

- **WHEN** 用户加载一个没有 `run_id` 的旧 checkpoint
- **THEN** 会话仍能加载，系统不得猜测并追加到任意既有运行文件
