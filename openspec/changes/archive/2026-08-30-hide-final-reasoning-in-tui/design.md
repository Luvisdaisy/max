## Context

`MaxGuiApp` 分别累积正文 `_stream_text` 与思考 `_stream_reasoning`，并由 `_refresh_live_stream`
在 `#live` 中渲染两者。当前 `_flush_live_stream` 将两项合成助手消息后调用 `_write_message`，而
`_write_message` 又会先渲染 `reasoning`；会话恢复也复用该方法。因此中间思考会在最终记录与历史
中再次出现。

会话存储与推理客户端需要继续保留并传递 `reasoning`：它们分别承担持久化和 provider 历史消息
编码，不是显示层的职责。

## Goals / Non-Goals

**Goals:**

- 保留 `#live` 对思考与正文的增量、分区展示。
- 让提交后的助手记录和恢复的助手历史只显示正文（及既有附件摘要）。
- 保持工具消息在记录区可见，并以测试锁定两种显示阶段的差异。

**Non-Goals:**

- 不停止上游生成、接收、持久化或向兼容 provider 回传 reasoning。
- 不改变工具调用协议、状态栏、会话 JSON 结构或 CLI 配置。
- 不新增“显示思考”的运行时开关。

## Decisions

### 1. 以消息写入记录区作为最终显示边界

仅调整 `_write_message` 对 `role=assistant` 的渲染：忽略 payload 内的 `reasoning`，保留现有正文和
附件摘要。`_refresh_live_stream` 继续使用两个累计缓冲区，因而流式展示不受影响。相比在
`_flush_live_stream` 删除字段，这一边界同时覆盖流式提交、非流式助手消息和会话恢复，且不会破坏
内存会话数据。

### 2. 保留 flush payload 的 reasoning 字段

`_flush_live_stream` 仍将 reasoning 放入要提交的助手 payload，交由既有会话／运行链路持久化。
相比只为显示构造无 reasoning 的 payload，此方式不会意外改变 SessionStore 记录或后续
`InferenceClient` 的 provider 专属历史编码。

### 3. 用 UI 测试分别覆盖实时与最终状态

更新现有双 think 测试以断言记录区不含思考、工具结果仍可见；更新会话恢复测试以断言历史
reasoning 不显示。保留或补充流式断言，确认 `#live` 在 think 尚未提交时仍含「思考」与思考内容。

## Risks / Trade-offs

- [用户无法在回合完成后从 TUI 回看思考] → 这是本变更的显示目标；原始 reasoning 仍在会话数据中。
- [仅修改 flush 导致恢复路径遗漏] → 统一在 `_write_message` 过滤，并用恢复测试覆盖。
- [误将 reasoning 删除而影响 provider 回放] → 测试与设计明确保留提交 payload 和会话存储。

## Migration Plan

1. 修改 TUI 渲染与相关测试。
2. 执行目标 TUI 测试及 Ruff 格式化、检查。
3. 回滚时恢复助手记录区对 `reasoning` 的渲染；已有会话数据无需迁移。

## Open Questions

无。
