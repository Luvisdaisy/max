## Context

当前 Agent 以 `think → act → observe → think` 运行，每次推理发送中文系统契约、当前任务用户消息、最近六个完整工具调用链和最新一张图片。默认注册表约有十一项工具，全部在每次 `think` 中发送。工具参数只做宽松 JSON 解析，`MAX_GUI_TOOL_TIMEOUT` 尚未施加到 `invoke`。模型没有返回工具调用时，图直接以 `done` 结束；运行事件虽然已有 `business_verified` 字段，但固定为假。

WSL Ollama 的实际上下文窗口为 256K，即 262144 token。该容量足够覆盖目前多数短任务，但不能替代请求预算：图像、工具 schema、长定位结果和多轮工具链仍会持续增长，而且模型输出必须预留空间。Ollama OpenAI 兼容请求不能通过项目现有 `MAX_GUI_MAX_MODEL_LEN` 改变服务端上下文，因此客户端只把 262144 当作已知容量边界，不尝试重配远端服务。

## Goals / Non-Goals

**Goals:**

- 在 262144 token 容量内保留完整且合法的最近工具链，预留输出和安全余量。
- 减少每轮不相关工具 schema，并在分发层再次校验工具是否属于当前阶段。
- 从运行时保证同一观察最多执行一个副作用工具，副作用后必须先观察。
- 为 GUI 副作用任务增加机器可识别的完成声明与最小证据门。
- 让工具参数错误、未知工具、超时与实现异常形成统一结构化结果。

**Non-Goals:**

- 不修改 WSL Ollama 的 `num_ctx`、监听、防火墙或模型文件。
- 不增加跨任务长期记忆、向量库、多 Agent、独立规划模型或视觉验证模型。
- 不把模型的视觉判断包装成确定性业务成功；完成门只保证声明、动作与后置观察闭环存在。
- 不改变现有桌面坐标换算、定位编号生命周期和无需弹窗确认的既有产品策略。

## Decisions

### 1. 使用保守估算的请求预算，而非固定调用链条数

配置新增 `context_window`、`max_output_tokens` 与 `context_safety_margin`。Ollama provider 的 `context_window` 固定为 262144；其它保留云端 provider 在注册表使用保守的 32768，避免把只服务 OCR vLLM 的 `MAX_GUI_MAX_MODEL_LEN` 误当成主推理容量。客户端发送 `max_tokens=max_output_tokens`，上下文选择器以：

`context_window - max_output_tokens - context_safety_margin - image_reserve`

作为消息与工具 schema 可用预算。估算器只统计可序列化文本和 schema 字符，采用保守的字符／token 比率，并为唯一内联图片使用固定预留。它不是 tokenizer 精确计数；真实 usage 继续作为运行观测，而不是下一次请求的唯一依据。

选择轻量估算而非加载 Qwen tokenizer，是为了避免主进程加载模型资产、增加启动耗时或让远程 provider 依赖本地 tokenizer。固定“最近六链”仍作为内存上限，但模型输入改为从最近向前逐链装入，任何链都不得拆开。当前用户消息、system 和动态工具 schema 本身已超过预算时，推理前直接给出中文 `ContextBudgetExceededError`。

### 2. 工具阶段由当前有效截图与完成状态推导

`Tool` 增加 `side_effect` 元数据；注册表可按名称返回 schema 和查询元数据。没有活动 `ViewFrame` 时只暴露 `screenshot`、`screen_info` 以及可处理显式附件的图像／OCR 工具；存在活动帧后开放定位和桌面动作。只有当前任务已经执行成功的副作用且取得后置截图时，才开放新的控制工具 `task_complete`。

阶段过滤同时发生在 schema 生成和 `act` 分发，避免模型通过幻觉名称绕过动态工具门。备选方案是只在 system prompt 描述阶段；它无法形成机器强制边界，因此不采用。

### 3. 一批调用最多执行第一个副作用

`act` 保持响应顺序：执行第一个副作用之前的只读调用和该副作用，随后所有调用统一返回 `action_batch_blocked`，不再触发实现。这样每个 OpenAI `tool_call_id` 都仍有配对结果，同时副作用后一定先进入 `observe` 和下一次 `think`。只读调用不在本变更中并行，避免引入共享截图／OCR 运行时竞态。

`mouse_move` 也按副作用处理，因为它改变真实桌面状态并生成新的活动帧；`screenshot`、`screen_info`、图像、OCR、`locate` 与 `task_complete` 为非副作用。

### 4. 用 `task_complete` 控制工具建立最小完成门

纯对话和只读观察任务仍允许以普通无工具正文结束。任务一旦成功执行过副作用，`TaskContext` 就写入 `completion_required=true`。模型必须在看过该副作用的后置截图后调用 `task_complete`，参数包含短摘要与截图中可见的完成证据。注册表先做严格参数校验；Agent 再检查最近成功副作用确实有后置截图。通过后 `observe` 直接转为 `done`，不再额外调用模型。

模型在需要完成声明时只返回正文，图不会误报成功：它保留正文、把完成门状态写入任务胶囊并再次 `think`；该次重试计入迭代上限。该设计不判断业务语义真假，但比“无工具即完成”多了可审计声明和后置观察前置条件。

### 5. 结构化错误保持模型可读文本兼容

`ToolResult` 增加 `ok` 与 `code`，成功默认 `ok=true/code=ok`；未知工具、阶段拒绝、参数错误、批次拒绝、超时和实现异常返回 `ok=false` 与稳定错误码，同时 `text` 保留中文说明。Agent 把 `ok/code` 写入 tool 消息 `exec`，并继续把 `text` 发送给模型。

JSON Schema 校验实现当前工具使用到的受限子集：对象、数组、字符串、整数、数值、布尔、必填、枚举、最小数组长度和附加属性拒绝。`Tool.schema()` 会递归给对象 schema 补 `additionalProperties=false`，避免逐个工具遗漏。工具执行使用 `asyncio.wait_for` 应用配置超时。

### 6. 运行事件只新增计数和判定

`model.started/completed` 增加上下文容量、估算输入、可用预算、动态工具数和裁剪链数；`tool.failed` 记录稳定错误码；`observation.completed` 记录完成门是否需要、是否通过。不得记录完整 prompt、schema、截图 base64、键盘正文或 `task_complete.evidence` 原文。

## Risks / Trade-offs

- [字符估算与真实 tokenizer 有误差] → 使用 256K 容量、输出预留、图片预留和安全余量四层保护，并保留真实 usage 观测。
- [动态工具过少影响附件任务] → 无桌面帧阶段仍保留图像与 OCR 观察工具，分发失败返回可恢复错误。
- [9B 模型忘记调用 `task_complete`] → system 和任务胶囊同时提示；缺少声明时重试且受迭代上限约束。
- [批次后续调用被拒绝增加一轮延迟] → 优先保证每次副作用后的新观察，不执行基于陈旧画面的动作。
- [`task_complete` 证据仍由模型描述] → 明确它是最小闭环而非独立视觉裁判，后续可用任务特定 evaluator 替换。

## Migration Plan

1. 增加向后兼容的配置和 Tool／TaskContext 可选字段，旧 session 缺字段时使用安全默认值。
2. 先启用严格工具结果、超时和动态 schema，再启用批次副作用限制与完成门。
3. 用 mock 请求验证 262144 容量、`max_tokens`、预算诊断和完整 tool 配对；用假桌面验证副作用门。
4. 回滚时可移除动态过滤与完成门，已有 session 中新增字段会被旧读取逻辑忽略。

## Open Questions

无。首版 Ollama 上下文容量固定为 262144，输出预留默认 8192，安全余量默认 4096，单张图片额外预留 8192 token。
