## ADDED Requirements

### Requirement: provider 上游思考开关映射

客户端每次向已注册 provider 发起 `/chat/completions` 请求时，MUST 根据
`Settings.enable_thinking` 与 provider 定义在 JSON 顶层加入控制上游生成思考的字段：
`ollama` 使用 `think` 布尔值；`modelscope` 与 `dashscope` 使用 `enable_thinking` 布尔值；
`openrouter` 使用 `reasoning.enabled` 布尔值；`qiniu` 使用 `thinking.type`，其值为
`enabled` 或 `disabled`。客户端 MUST NOT 使用 `extra_body` 包装这些字段。该配置 MUST NOT
改变 reasoning 的 SSE 解析、展示或既有 DashScope 历史 `reasoning_content` 回传行为。

#### Scenario: 默认关闭七牛上游思考

- **WHEN** `MAX_PROVIDER=qiniu` 且未设置 `MAX_GUI_ENABLE_THINKING`
- **THEN** POST 请求的 JSON 含 `thinking` 为 `{ "type": "disabled" }`

#### Scenario: 开启 OpenRouter 上游思考

- **WHEN** `MAX_PROVIDER=openrouter` 且 `MAX_GUI_ENABLE_THINKING=true`
- **THEN** POST 请求的 JSON 含 `reasoning` 为 `{ "enabled": true }`

#### Scenario: 映射 DashScope 开关

- **WHEN** `MAX_PROVIDER=dashscope` 且 `MAX_GUI_ENABLE_THINKING=false`
- **THEN** POST 请求的 JSON 顶层含 `enable_thinking` 为 `false`

#### Scenario: 上游拒绝关闭字段

- **WHEN** 上游以非 2xx 响应拒绝该 provider 的关闭思考字段
- **THEN** 客户端沿用现有 HTTP 错误链路展示状态码与截断后的响应体，且 MUST NOT 静默改为开启思考或移除字段重试
