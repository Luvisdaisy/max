## MODIFIED Requirements

### Requirement: GUI 系统契约注入

每次 `think` 发给模型的消息列表 MUST 以一条中文 `role=system` 消息开头。该消息 MUST 要求：还没有画面时先 `screenshot`；要点、拖、输入前先 `mouse_move`，根据回注图上的光标判断位置，对了再调用不带坐标的 `mouse_click` 或拖拽/键盘；看到回注图后 MUST 先判断红十字落在哪个控件上，与目标不一致则再 `mouse_move`，MUST NOT 在未看图时点击；坐标只用最近一帧视图像素或 `ocr_locate` 的 `target_id`，且视图像素必须落在该帧 `view_width`×`view_height` 内；不要用逻辑分辨率、屏幕百分比、归一化坐标，也不要把工具摘要里的逻辑坐标再当输入；看不清字再 OCR；破坏性桌面动作一次一个；动作后根据新画面判断是否进入下一子任务；首轮尽量输出编号子任务。该消息 MUST 写明当前操作系统的中文名称；当主机为 macOS 时 MUST 写明不是 Windows，快捷键用 `command` 而不是 `windows`。若当前会话已有视图帧，该消息 MUST 包含该帧的 `view_width` 与 `view_height`。该 `system` 消息 MUST NOT 写入会话 JSON，MUST NOT 作为 TUI 记录区条目出现。

#### Scenario: think 请求带 system

- **WHEN** Agent 进入 `think` 并调用推理客户端
- **THEN** 请求的 `messages` 第一条 `role` 为 `system`，正文含「先截图」、先移鼠看光标、视图像素约定与视图宽高边界

#### Scenario: 会话不保存 system

- **WHEN** 一回合结束并落盘
- **THEN** 该会话 JSON 的 `messages` 中没有 `role` 为 `system` 的条目

#### Scenario: macOS 上标明不是 Windows

- **WHEN** 主机为 macOS，Agent 进入 `think`
- **THEN** 系统消息含「macOS」，且含「不是 Windows」或等价说明，以及使用 `command` 而非 `windows`

#### Scenario: 有视图帧时写出宽高

- **WHEN** 当前会话视图为 1536×864，Agent 进入 `think`
- **THEN** 系统消息含 `1536` 与 `864`
