## Context

LangGraph 仍是 `think ⇄ act → observe`。`to_chat_messages` 会把历史里每一张仍存在的截图编进请求；仓库没有 `role=system`；`max_iterations` 默认 8；变异桌面工具只回文本。会话 JSON 原先只有对话，工具逐步监控缺字段。第一期要在这张图上加 GUI 协议，并把逐步执行嵌进 tool 消息，不换框架。

约束：OpenAI 兼容 tool 消息必须对应助手 `tool_call_id`；TUI 按会话消息渲染，故 system 不得写入会话；`artifacts/` 已在 gitignore。

## Goals / Non-Goals

**Goals:**

- 4B 每次 think 都看到同一份中文 GUI 契约。
- 8k 上下文里最多两张实图，更早截图变成摘要。
- 点、拖、滚、键成功后模型能立刻看到新画面（同一条 tool 结果）。
- 状态里有可检查的 `plan` / `current_subtask`。
- 每步工具调用的耗时、参数、错误写在会话 tool 消息的 `exec` 里，便于数「是否先截图、点后是否有新图」。

**Non-Goals:**

- 独立 `plan` 节点、第二张图、换 LangChain。
- 数据集、LoRA、新桌面工具。
- 同屏空转熔断、工具自动重试。
- 提高 `max_model_len`（须重启 vLLM）。
- 执行日志查看器。

## Decisions

### 1. System 只在请求时注入

`think` 调用 `to_chat_messages(..., system=GUI_SYSTEM_PROMPT)`，把 `role=system` 插到编码结果最前。状态与会话 JSON 不存这条消息。

备选：写入会话。否决原因：TUI 会当普通消息刷屏，改文案还会污染旧会话。

契约要点（固定中文，模块常量）：必须先 `screenshot`；坐标只用最近一帧视图像素或 `ocr_locate` 的 `target_id`；看不清字再 OCR；破坏性动作一次一个；动作后根据新图判断是否进入下一子任务；首轮尽量给出编号子任务。

### 2. 历史只保留最近两张实图

在 `to_chat_messages` 里按消息顺序收集所有仍存在的本地图（用户附件与 tool/assistant 回注）。**全局最后 2 个文件**编 `image_url`；更早的从图部件拿掉，文本追加一行「历史截图已省略：路径，视图宽×高」（宽高能从磁盘或既有摘要读到则写上）。缺文件仍只发文本。

会话落盘与 TUI 展示不变。N=2 而不是 1，是为了动作前后对比。

这是对「每张仍存在的图都回注」的有意收窄。

### 3. 变异动作把新截图附在同一条结果上

`mouse_click` / `mouse_drag` / `mouse_scroll` / `keyboard_type` / `keyboard_press` 在后端成功后，内部再截一次屏（复用现有截图落盘、坐标系、预处理）。返回 `ToolResult(text=原摘要 + 新图摘要, images=[新 PNG])`。用户取消、权限失败或动作抛错则不截。`mouse_move` / `screen_info` / 显式 `screenshot` 行为不变。

备选：`act` 里再插一次独立 `screenshot` 调用。否决原因：没有对应的 assistant `tool_call_id`，和模型自己的截图重复。

后置截图失败（黑图/权限）：保留动作文本，附中文错误，不把空图发给模型。

### 4. 轻量 Plan：状态字段 + 规则，不加节点

`AgentState` 增加 `plan: list[str]`、`current_subtask: str | None`（`total=False`，旧 checkpoint 可缺）。拓扑仍是 think/act/observe。

- 助手文本出现至少两行「数字 + `.` 或 `)` + 内容」时，覆盖 `plan`，`current_subtask` 取第一项。
- 工具失败：不改当前子任务。
- 助手文本含「改计划」且带新编号列表：覆盖 `plan` 并重置到第一项。
- 助手文本含「子任务完成」或「下一子任务」且 `plan` 非空：下标加一（不超过末项）。

不做第二轮模型 Evaluate。解析失败则字段保持原值，不阻断循环。

### 5. 迭代上限默认 20

`Settings.max_iterations` 与 `MAX_GUI_MAX_ITERATIONS` 缺省从 8 改为 20。测试仍可钉死较小值。不区分「桌面 / 文件」两套上限。同屏空转检测留到后续变更。

### 6. 执行信息嵌在会话 tool 消息里

不写 `artifacts/runs/`。`act` 把每次工具结果收成字典（纯字符串结果也包一层 `text`），并加上：

```json
{
  "name": "screenshot",
  "exec": {
    "iteration": 0,
    "subtask": null,
    "arguments": {},
    "duration_ms": 12,
    "error": null,
    "has_image": true
  }
}
```

`arguments` 只留可 JSON 序列化的短字段，过长截断。不写图像字节。`created_at` 沿用消息时间。编码发给模型时只使用 `text` / `images`，丢掉 `exec`。TUI 记录区只展示 `text`。旧会话缺 `exec` 仍能加载。

备选：独立 JSONL。否决原因：对轨迹时要同时打开会话和 runs 文件，字段还要对 `tool_call_id`。

## Risks / Trade-offs

- [4B 忽略 system / 不写计划] → 运行时仍强制后置截图与裁剪图像；plan 解析失败不致命。
- [每步多一次全屏截图，延迟上升] → 只挂在变异动作成功路径；换独立 screenshot 调用不会更便宜。
- [后置截图更新坐标系，模型若用「点击前那张图」的坐标会偏] → 契约写明只用最近一帧；保留最近两张图便于它对照。
- [编号列表误解析] → 要求至少两行编号；无匹配则不动字段。
- [8k 仍可能爆] → 先靠两图上限；加 `max_model_len` 要重启服务，本期不做。
- [确认门之后才截图] → 取消路径不截，避免未授权动作留下新坐标系。

## Migration Plan

- 旧会话无 `plan` 字段即可恢复。
- 默认迭代 20 只影响新进程；环境变量仍可覆盖。
- 无需数据迁移。回滚：去掉 system 注入、裁剪、后置截图与 `exec` 字段，行为回到本期之前。

## Open Questions

无。探索阶段已选定：后置截图附在同一条 tool 结果；Plan 方案 A；保留 2 张图；执行信息进会话 `exec`、不要独立 runs。
