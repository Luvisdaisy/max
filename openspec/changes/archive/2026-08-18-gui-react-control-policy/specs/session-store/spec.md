## ADDED Requirements

### Requirement: 工具消息持久化执行元数据

`role` 为 `tool` 的会话消息 MUST 在 `content` 中保存工具名 `name` 与嵌套对象 `exec`。`exec` MUST 至少包含：`iteration`、`subtask`（无计划时为 `null`）、`arguments`（可 JSON 序列化的短对象；过长 MUST 截断）、`duration_ms`、`error`（无错误为 `null`）、`has_image`。MUST NOT 把图像字节或 base64 写入 `exec`。MUST NOT 另写 `artifacts/runs/` 执行日志。缺少 `exec` 的旧会话 MUST 仍能加载。发给模型时 MUST NOT 把 `exec` 编进请求正文。

#### Scenario: 截图写入 exec

- **WHEN** Agent 成功执行一次 `screenshot` 并保存会话
- **THEN** 对应 tool 消息 `content.name` 为 `screenshot`，`content.exec.has_image` 为真，`content.exec.error` 为 `null`，且项目下不因此创建 `artifacts/runs/` 文件

#### Scenario: 工具错误仍写入 exec

- **WHEN** 工具返回错误文本或业务失败
- **THEN** 该 tool 消息 `content.exec.error` 为非空字符串，且会话仍保存该条消息

#### Scenario: 旧会话缺 exec

- **WHEN** 已存 tool 消息没有 `exec` 字段
- **THEN** store 成功加载该会话
