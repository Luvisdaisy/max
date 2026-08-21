## MODIFIED Requirements

### Requirement: GUI 系统契约注入

每次 `think` 发给模型的消息列表 MUST 以一条中文 `role=system` 消息开头。该消息 MUST 要求：还没有画面时先 `screenshot`；要点、拖、输入前先 `mouse_move`，根据回注图上的光标判断位置，对了再调用不带坐标的 `mouse_click` 或拖拽/键盘；坐标只用最近一帧视图像素或 `ocr_locate` 的 `target_id`，且视图像素必须落在该帧 `view_width`×`view_height` 内；不要用逻辑分辨率、屏幕百分比、归一化坐标，也不要把工具摘要里的逻辑坐标再当输入；看不清字再 OCR；破坏性桌面动作一次一个；动作后根据新画面判断是否进入下一子任务；首轮尽量输出编号子任务。该 `system` 消息 MUST NOT 写入会话 JSON，MUST NOT 作为 TUI 记录区条目出现。

#### Scenario: think 请求带 system

- **WHEN** Agent 进入 `think` 并调用推理客户端
- **THEN** 请求的 `messages` 第一条 `role` 为 `system`，正文含「先截图」、先移鼠看光标、视图像素约定与视图宽高边界

#### Scenario: 会话不保存 system

- **WHEN** 一回合结束并落盘
- **THEN** 该会话 JSON 的 `messages` 中没有 `role` 为 `system` 的条目

## ADDED Requirements

### Requirement: think 推理异常结束为 error

`think` 调用推理客户端失败时 MUST 将图状态设为 `error`，写入人类可读错误，MUST NOT 把未捕获异常甩出图外导致会话仍为上一回合的 `done`。

#### Scenario: 流式 HTTP 错误变成会话错误

- **WHEN** `/chat/completions` 返回非 2xx
- **THEN** `AgentRunner.run` 返回的状态 `status` 为 `error`，且该状态被写入当前会话
