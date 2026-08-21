## Context

会话 `20260821-095256` 里，模型要打开 Dock 上的 Chrome。过程中每次 `mouse_click` 都要 TUI 确认；模型把 `y` 估在视图底部（780–855），工具却报告落点约为 `(x, 647)`。根因有两层：

1. 模型调用 `screenshot` 时带了 `region: 2560×1440`，而主屏逻辑尺寸是 1920×1080。落盘 PNG 实际是 1920×1080，但视图帧把逻辑高写成 1440。换算 `y_view * 1440 / 864` 超出 1080，再夹紧，反算回视图就是 647。四次点击都是这个数。
2. 点击后的全屏截图已经按 1920×1080 写进了进程缓存，但 `active_view_frame()` 优先读 ContextVar。LangGraph 每个节点从父上下文拷贝，父里仍是第一张超界截图的帧；`run()` 的 `finally` 再用这份过期帧把会话 JSON 盖回去。

第四次点击之后没有助手终态，`status` 仍是上一回合的 `done`，检查点停在「截全屏」那一轮。TUI 只在 `except` 里打印 `运行失败：…`，不写会话。同时 `to_chat_messages` 回注最近两张 1536 边长图，加上越积越多的思考正文，在默认 `max_model_len=8192` 下很容易让下一轮 `think` 被推理服务 400 掉。

## Goals / Non-Goals

**Goals:**

- 工具执行不再等人点允许。
- 点、拖、打字、按键前，模型必须先看到带光标标注的截图。
- 视图坐标系与真实主屏一致；超界 `region` 不得污染换算。
- 进程内坐标系以会话缓存为准，不被父 ContextVar 盖住。
- `think` 失败写入会话 `error`，检查点与状态与当时消息一致。
- 每个请求只回注最近一张图，降低多轮顶满上下文的概率。

**Non-Goals:**

- 不提高默认 `max_model_len`，不换模型。
- 不新增加「确认光标」工具名。
- 不训练或微调坐标能力；用协议强迫先移鼠再看图。
- 不删除会话 JSON 里的 `auto_approve` 字段（避免旧文件无法加载）。
- 不改 OCR / 文件路径沙箱。

## Decisions

### 1. 去掉确认门，而不是默认打开自动批准

把 `mouse_click`、`mouse_drag`、`mouse_scroll`、`keyboard_type`、`keyboard_press`、`write_file` 的 `confirmation_scope` 设为 `none`。TUI 不再 `push_screen_wait(ConfirmScreen)`。

备选是把两个 `auto_approve*` 默认改成真：开关还在，漏改一处测试仍会弹框。本次目标是「所有工具都不批准」，直接取消确认更干净。字段仍读写，缺省 `false`，只是不再被询问。

### 2. 先 `mouse_move` 看光标，再在当前位置点/拖/输入

`mouse_move` 成功后必须按现有 `screenshot` 规则截一帧（含光标十字）、更新视图帧并回注图像。这是验证光标的唯一入口。

`mouse_click` **BREAKING**：不再接受 `x`/`y`。给出坐标则返回中文错误，要求先 `mouse_move`。只点击当前指针；仍可使用 `target_id`（定位中心视为已给出目标，移动并点击，但点击前仍先截图验证——见下）。为避免一次调用里既动又点、模型看不见光标：带 `target_id` 的点击改为「移到该点 + 截图 + **不点击**」，文案说明下一步再调无参数 `mouse_click`。这样所有点击都经过一帧光标图。

更简单的实现（采用）：`target_id` 与坐标一样，只允许出现在 `mouse_move`。`mouse_click` 零坐标、零 `target_id`，只点当前位置。

`mouse_drag` **BREAKING**：不再要 `x1`/`y1`。起点为当前指针；只需 `x2`/`y2`（视图像素，仍走视图边界校验）。调用时若最近一帧不是 `mouse_move` 产生的，拒绝并要求先移鼠。

`keyboard_type` / `keyboard_press`：若本会话还没有成功的光标截图（`mouse_move` 或 `screenshot`），拒绝。不在同一次调用里先截再输入——验证必须让模型看完再发下一轮工具。

`mouse_scroll`：与点击一致，可选坐标改为必须先 `mouse_move`；本次只要求去掉确认，滚动仍可带 `x`/`y` 以免范围膨胀。若实现时顺手与点击对齐，也可以只滚当前位置。

系统提示改为：要操作时先 `mouse_move`，根据回注图判断红十字是否在目标上，对了再 `mouse_click` / `mouse_drag` / 键盘；错了就再 `mouse_move`，不要猜着点。

### 3. 截图 `region` 夹紧到主屏，逻辑尺寸以夹紧后为准

`screenshot` 先读 `backend.size()`。`region` 缺省即主屏。若给出区域：原点夹到屏内，宽高截断到剩余空间，且至少 1×1。逻辑宽高用夹紧后的值，再用 `image.width / logical_w` 算 scale。模型再传 2560×1440 时，帧是 1920×1080，底部 Dock 的视图像素才能映射到真正的底部。

### 4. 视图帧以会话进程缓存为准

`store_view_frame` 仍写 ContextVar 与 `_session_view_frames`。`active_view_frame()` 改为 **先读会话缓存，再读 ContextVar**。`run()` 的 `finally` 不得用过期 ContextVar 覆盖磁盘上较新的帧：`snapshot_desktop_context` 必须走同一套 `active_view_frame()`。每个 `think`/`act` 节点开始时用当前会话 id 对齐缓存，避免父上下文把第一张超界图送回来。

### 5. `think` 异常变成 `error` 状态而不是冒泡

`client.stream` 的 `RuntimeError` / `ConnectionFailedError` 在 `think` 内捕获，写入 `state["error"]`、`status="error"`，可选追加一条助手说明，然后结束图。`run()` 正常走到 `_persist`。TUI 已有 `status=="error"` 分支。禁止只在终端打「运行失败」而会话仍是 `done`。

### 6. 只回注最近一张图

`MAX_INLINE_IMAGES` 从 2 改为 1。更早的图改成路径摘要。4B + 8192 上下文下两张 1536 边长图加上多轮思考正文，是这次多轮失败最可能的触发条件。不在本变更里提高服务端上下文。

## Risks / Trade-offs

- [点一次要多一轮 ReAct] → 换正确率；4B 目测坐标不可靠，这是故意的。
- [去掉确认后误操作桌面] → 本工具本就是本机 Agent；用户明确要求全自动。危险热键（Command-Q 等）仍拒绝。
- [只回注一张图，模型看不到对比] → 动作后置截图仍会成为「最近一张」，足够判断成败。
- [捕获 `think` 异常后图结束，用户要重发] → 好过状态撒谎；可 `/interrupt` 后的恢复路径仍可用检查点。
- [旧会话 JSON 仍带 `auto_approve: false`] → 加载不崩，只是不再弹框。

## Migration Plan

无需迁移脚本。旧会话打开即按新工具 schema 跑；模型若仍对 `mouse_click` 传 `x`/`y`，会收到中文错误并应改调 `mouse_move`。

回滚：恢复确认 scope、`mouse_click` 坐标、`MAX_INLINE_IMAGES=2` 与 `active_view_frame` 的 ContextVar 优先顺序。

## Open Questions

- 无。滚动是否也强制先 `mouse_move` 留到实现时按最小改动处理：保持可带坐标，但不再确认。
