## Context

`InferenceClient` 当前固定发送模型、消息、流式、用量和工具 schema，并只被动解析上游的
`reasoning_content`／`reasoning`。`ProviderDefinition` 已是后端差异的唯一来源，适合承载
thinking 请求映射；`replay_reasoning` 则只负责 DashScope 的历史消息回传，不能复用为开关。

## Goals / Non-Goals

**Goals:**

- 提供 `MAX_GUI_ENABLE_THINKING`，缺省 `false`，并在每次主推理请求中显式控制上游思考。
- 让不同供应商的非标准字段保持在 provider 定义中，不在客户端散落名称判断。
- 保持已有 reasoning 的流式解析、展示和会话持久化行为。

**Non-Goals:**

- 不提供思考预算、推理强度或 TUI 运行时切换。
- 不把“关闭上游思考”误实现为隐藏已返回的 reasoning。
- 不保证仅思考模型接受关闭；上游拒绝须按既有 HTTP 错误链路可见地报告。

## Decisions

### 1. 使用严格布尔的统一环境变量

`MAX_GUI_ENABLE_THINKING` 接受不区分大小写的 `true`／`false`；缺失等同于 `false`，任何
其它非空值在配置加载时中文报错。`Settings.enable_thinking` 保存解析结果，测试可直接构造
该字段。相比“缺省时不发送参数”，显式 `false` 才能满足关闭上游生成思考的语义。

### 2. provider 声明请求负载映射

`ProviderDefinition` 新增一个无副作用的方法或不可变映射，按布尔值生成额外 JSON 字段：

| provider | `false` | `true` |
|---|---|---|
| `ollama` | `{"think": false}` | `{"think": true}` |
| `modelscope` | `{"enable_thinking": false}` | `{"enable_thinking": true}` |
| `dashscope` | `{"enable_thinking": false}` | `{"enable_thinking": true}` |
| `openrouter` | `{"reasoning": {"enabled": false}}` | `{"reasoning": {"enabled": true}}` |
| `qiniu` | `{"thinking": {"type": "disabled"}}` | `{"thinking": {"type": "enabled"}}` |

客户端把该映射合并至请求顶层；不发送 SDK 专属的 `extra_body` 包装。对 OpenRouter 的嵌套
对象采用一次性赋值，避免与未来的推理强度设置产生浅合并歧义。

### 3. 不改变历史 reasoning 回传

`replay_reasoning` 维持现有语义：仅 DashScope 将历史助手 reasoning 写入
`reasoning_content`。这与新开关独立；即使本轮关闭思考，旧会话中已有的 reasoning 也按既有
provider 契约编码，不删除会话数据。

## Risks / Trade-offs

- [部分模型或旧服务版本不接受关闭字段] → MockTransport 测试锁定本地负载；真实服务的 4xx
  保留状态码与响应体，且不静默重试为“开启”。
- [思考模型不能关闭] → 该上游错误明确暴露；不以隐藏输出伪装为关闭成功。
- [显式字段改变默认上游行为] → 这是用户要求的默认关闭；`.env.example` 与 README 明确说明。

## Migration Plan

1. 部署后无须修改现有 `.env`，缺省即关闭；需要推理时加入
   `MAX_GUI_ENABLE_THINKING=true`。
2. 先执行配置与 MockTransport 合约测试，再以各真实密钥分别验证文本、图片和工具请求。
3. 回滚时删除新变量与 payload 映射；不影响已有会话记录。

## Open Questions

无。
