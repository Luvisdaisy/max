## Context

模型当前通过 native `tool_calls` 驱动 Agent，但 system 同时要求正文输出带 `thought` 和文本工具调用的 JSON。服务端未提供独立 reasoning 字段时，这些内部文字全部进入 `content`，TUI 只能如实展示。

## Goals / Non-Goals

**Goals:**

- 让简单对话始终产生直接、可读的正式回复。
- 让 GUI 操作依旧遵守截图核验和原生工具调用流程。
- 保留提供方独立 reasoning 字段的现有展示兼容。

**Non-Goals:**

- 不新增模型输出解析器，不从普通正文猜测或剥离思考。
- 不改变工具 schema、会话格式、上下文裁剪或 TUI 布局。

## Decisions

### 1. 正文是唯一用户可见答复，工具只走 native 调用

删除 JSON 输出模板、`thought` 和文本 `tool_calls` 要求。提示词明确要求模型：无工具时只输出简洁答复；
需要操作时借助 API 原生工具调用，正文只写短状态或完成结论。

备选方案是保留 JSON 后在客户端解析 `answer` 字段。否决原因：兼容模型可能继续在 JSON 外输出文本，解析会
新增脆弱的双协议和失败模式。

### 2. 不将普通正文伪装成 reasoning

仅 SSE 独立字段 `reasoning_content`／`reasoning` 进入 TUI 思考区。普通 `content` 一律作为正式助手正文，
靠提示词杜绝内部推演，而非启发式过滤。

## Risks / Trade-offs

- [模型仍长篇解释] → 提示词限定执行中状态和完成结论长度，并用回归测试防止 JSON 合同复发。
- [模型在正文描述工具而不调用] → 重申工具必须走 native 调用；现有工具循环与安全 gate 不变。

## Migration Plan

无需迁移。旧会话保留原消息；回滚仅恢复原提示词，但会重新出现对话质量问题。

## Open Questions

无。
