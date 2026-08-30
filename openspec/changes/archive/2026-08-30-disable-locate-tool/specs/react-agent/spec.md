## MODIFIED Requirements

### Requirement: 系统契约引导复用当前帧定位

每次 `think` 的 GUI 系统契约 MUST 要求模型先取得并阅读最新截图，再使用该截图中的视图像素调用 `mouse_move`。契约 MUST NOT 要求或推荐已禁用的定位工具、`target_id` 或定位编号；需要确认控件文字时 MUST 指导模型调用 `ocr`。移动后模型 MUST 依据后置截图的光标核验决定是否调用无坐标的 `mouse_click`。

#### Scenario: 只用视图像素移动

- **WHEN** 当前任务需要点击图标或按钮
- **THEN** system 提示模型使用当前截图视图像素调用 `mouse_move`，且不要求先调用 `locate`

#### Scenario: 需要读字时使用 OCR

- **WHEN** 截图中的控件文字无法直接读清
- **THEN** system 提示模型调用 `ocr` 获取文字，不调用 `locate`

### Requirement: GUI 系统契约注入

每次 `think` 发给模型的消息列表 MUST 以一条中文 `role=system` 消息开头。该消息 MUST 要求：桌面任务一律用键鼠完成；每一次键鼠动作都必须截图核验；还没有画面时先 `screenshot`；要点、拖、输入前先 `mouse_move`，根据回注图上的光标判断位置，对了再调用不带坐标的 `mouse_click` 或拖拽/键盘；看到回注图后 MUST 先判断红十字落在哪个控件上，与目标不一致则再 `mouse_move`，MUST NOT 在未看图时点击；坐标只用最近一帧视图像素，且视图像素必须落在该帧 `view_width`×`view_height` 内；不要用逻辑分辨率、屏幕百分比或归一化坐标，也不要把工具摘要里的逻辑坐标再当输入；看不清字再调用 `ocr`；MUST NOT 调用或尝试调用 `locate`；破坏性桌面动作一次一个；动作后根据新画面判断是否进入下一子任务；首轮尽量输出编号子任务。该消息 MUST 写明当前操作系统的中文名称；当主机为 macOS 时 MUST 写明不是 Windows，快捷键用 `command` 而不是 `windows`。若当前会话已有视图帧，该消息 MUST 包含该帧的 `view_width` 与 `view_height`。该 `system` 消息 MUST NOT 写入会话 JSON，MUST NOT 作为 TUI 记录区条目出现。

#### Scenario: think 请求带 system

- **WHEN** Agent 进入 `think` 并调用推理客户端
- **THEN** 请求的 `messages` 第一条 `role` 为 `system`，正文含「先截图」、视图像素约定与视图宽高边界，且不含 `target_id` 或定位编号

#### Scenario: 会话不保存 system

- **WHEN** 一回合结束并落盘
- **THEN** 该会话 JSON 的 `messages` 中没有 `role` 为 `system` 的条目
