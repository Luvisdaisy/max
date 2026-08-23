## Context

本地运行可观测性已经把每次用户任务拆成 `run_id`、结构化 JSONL 和 TUI 独立监控面板。`model.completed` 目前只记耗时、provider、model、finish reason 和正文字符数；推理客户端在 SSE `choices` 为空时直接丢弃该块，因此 OpenAI 兼容接口常见的流末 `usage` 根本进不了 Agent。

本变更建立在现有 `RunRecorder` / `RunEvent` / 监控面板之上，不新增事件类型，也不改会话 JSON。提供方包括本机 vLLM、魔搭和百炼兼容模式，用量字段以 Chat Completions 的 `usage` 为准。

## Goals / Non-Goals

**Goals:**

- 从流式补全中拿到每次调用的输入、输出、合计 token，并写入 `model.completed`。
- 在运行汇总和 JSONL 恢复中累计已知用量。
- 在默认监控面板展示本次运行累计用量，最近模型事件带上当次用量。
- 提供方不回传时明确为未知，不把缺失写成 0。

**Non-Goals:**

- 本地 tokenizer 估算、tiktoken 或按字符近似。
- 费用、汇率、单价配置。
- 把用量写入会话消息或记录区。
- 逐 token 持久化，或新增 `usage.*` 事件类型。
- 缓存 token、reasoning token 等扩展字段的独立展示（允许随 `usage` 原样忽略）。
- 远程指标、Prometheus 或跨进程聚合。

## Decisions

### 1. 只采信接口回传的 `usage`

用量来源仅限 Chat Completions 响应中的 `usage` 对象，读取 `prompt_tokens`、`completion_tokens`、`total_tokens`。三者都缺失则整次调用记为未知。`total_tokens` 缺失但输入输出都在时，合计等于二者之和。

备选：用本地 tokenizer 估算。否决原因：多模态请求含图像，字符数与真实 token 不对齐，还会引入新依赖。

### 2. 流式请求显式打开用量块

请求在 `stream: true` 时同时发送 `stream_options: { "include_usage": true }`。三种后端共用同一请求体。未知字段被忽略时，行为退化为「用量未知」，不得因此失败。

解析必须接受「`choices` 为空、仅含 `usage`」的 SSE 块；该块不得触发正文或思考回调。拼装后的 `ChatDelta` 携带可选用量；多次出现时以后一次完整对象为准。

备选：为取用量改成非流式。否决原因：会破坏现有 token 级 TUI 展示。

### 3. 沿用现有模型完成事件，不新增类型

`ChatDelta` 增加可选用量值对象。`AgentRunner` 在现有 `_emit_model_completed` 中写入：

- `prompt_tokens` / `completion_tokens` / `total_tokens`：非负整数
- 未知时三个字段都不出现，或显式为 `null`；实现选定一种并在记录器与 TUI 中按「缺省或 null 即未知」处理

`model.failed` 只有在失败前已经拿到 `usage` 时才写入；否则不加假数据。运行终态 `data` 增加累计 `prompt_tokens`、`completion_tokens`、`total_tokens`。累计只加已知调用；全程未知则终态这三个字段缺失或为 `null`。

`RunRecorder` 恢复 JSONL 时按同样规则累加，保证中断恢复后面板和终态连续。

备选：每次用量单独一条 `model.usage` 事件。否决原因：与「模型调用边界一条汇总」重复，增加热路径写入。

### 4. TUI 只在监控面板展示

独立运行监控面板增加一行中文用量：`用量：输入 N / 输出 M / 合计 T`。累计值随 `model.completed` 更新，终态事件以记录器汇总覆盖，避免重复累加。最近事件里模型完成写作 `模型完成 820ms 输入 N 输出 M`；当次未知则写 `用量未知`。

没有已知用量时面板显示 `用量：未知`，不得显示 `输入 0 / 输出 0`。会话记录区、底部一句状态栏和 tool 正文都不展示用量。

备选：把用量写入助手消息元数据。否决原因：会话是对话与 checkpoint 的事实来源，用量属于运行诊断，应留在 JSONL 与监控面板。

### 5. 请求体变更保持向后兼容

Mock 传输与测试必须断言或允许 `stream_options`。旧运行 JSONL 没有用量字段时，恢复后累计视为未知，现有耗时与工具统计不变。

## Risks / Trade-offs

- [部分提供方忽略 `stream_options`，永远看不到用量] → 面板与日志明确「未知」，不阻断推理；不在本变更引入按提供方的特殊协议。
- [部分提供方因未知字段返回 4xx] → 三种目标后端均为 OpenAI 兼容；若实测拒绝，再改为可关闭，而不是第一版就做重试分叉。
- [空 `choices` 用量块被误当成结束] → 用量块不得设置 `finish_reason`，不得触发 token 回调；`[DONE]` 与 `finish_reason` 仍按现有规则。
- [把未知写成 0 会低估云端费用] → 缺字段不加进累计，UI 用「未知」而不是 0。
- [监控面板信息变密] → 用量独占一行，不塞进状态栏，不增加新面板。

## Migration Plan

1. 扩展流式解析与 `ChatDelta`，补推理测试。
2. 记录器汇总与 `model.completed` 载荷接入用量，补恢复与终态测试。
3. 监控面板与最近事件展示用量，补 TUI 行为测试。
4. 更新 README 中监控面板说明。

回滚时去掉 `stream_options`、用量字段和面板那一行即可；旧 JSONL 仍可按现有信封读取。

## Open Questions

无。用量只采信接口回传、未知不记 0、只在监控面板展示，均已由本次需求范围确定。
