## MODIFIED Requirements

### Requirement: 截取主屏并返回逻辑元数据

`screenshot` MUST 截取主屏（或给定逻辑像素 `region`），把 PNG 写入 `artifacts/screenshots/`，并返回文本摘要：路径、逻辑宽高、发给主模型后的视图宽高、区域逻辑原点、`scale`、当前光标的**视图像素**坐标，以及 `coordinate_space` 为 `view`。全黑或过小的图像 MUST 视为屏幕录制权限失败，返回中文步骤，且 MUST NOT 把空图发给模型。默认 MUST 在图上标注当前光标位置。成功截图 MUST 更新后续鼠标工具使用的视图坐标系，且该坐标系 MUST 写入当前会话，以便后续用户回合与进程重启后恢复。

#### Scenario: 全屏截图成功

- **WHEN** 模型调用 `screenshot` 且屏幕录制已授权
- **THEN** 工具写入 PNG，摘要包含 `path`、逻辑宽高、`view_width`、`view_height`、`origin`、`scale`、`cursor`、`coordinate_space`，并附带该图像引用

#### Scenario: 摘要光标使用视图像素

- **WHEN** 全屏截图的逻辑尺寸为 1920×1080、视图为 1536×864，光标逻辑坐标为 (1282, 834)
- **THEN** 摘要 `cursor` 为换算后的视图像素 (约 1026, 667)，且 `y` 不超过 `view_height`

#### Scenario: 未授权得到黑图

- **WHEN** 截图结果全黑或尺寸过小
- **THEN** 工具返回屏幕录制授权的中文步骤，且不把该图作为模型输入

### Requirement: 视图像素换算为逻辑像素

`mouse_move`、`mouse_click`、`mouse_drag`、`mouse_scroll` 的坐标输入 MUST 解释为最近一次成功 `screenshot` 回注给主模型的那张图上的像素。工具 MUST 按该图的视图宽高、逻辑宽高与区域原点换算成逻辑像素，再交给桌面后端。换算后越界 MUST 夹紧到主屏内并在结果中说明。当前会话尚无成功截图时，输入 MUST 当作逻辑像素，并在结果中说明未做视图换算。该坐标系 MUST 在同一会话的后续用户回合中仍然有效，不得因 TUI worker 结束而丢失。

#### Scenario: 按视图像素点击

- **WHEN** 最近一次全屏截图的视图宽为逻辑宽的一半，模型批准后的 `mouse_click` 给出视图坐标 `(100, 40)`
- **THEN** 后端收到的逻辑坐标为 `(200, 80)`（在未夹紧的情况下）

#### Scenario: 区域截图后的局部坐标

- **WHEN** 最近一次截图 `region` 原点为逻辑 `(200, 100)`，视图与区域逻辑尺寸之比为 1，模型给出视图 `(10, 15)`
- **THEN** 后端收到的逻辑坐标为 `(210, 115)`

#### Scenario: 下一用户回合仍按视图像素换算

- **WHEN** 上一回合已成功全屏截图且视图宽为逻辑宽的一半，新回合在未再截图的情况下调用 `mouse_move` 给出视图 `(100, 40)`
- **THEN** 后端收到的逻辑坐标为 `(200, 80)`，结果说明已从视图像素换算，且 MUST NOT 写「尚无截图」

#### Scenario: 按定位编号点击

- **WHEN** 最近一次 `ocr_locate` 成功且含 `id=1`，用户批准 `mouse_click` 且 `target_id` 为 `1`
- **THEN** 指针移到该项的逻辑中心并点击，不使用本次调用中的 `x`/`y`

## ADDED Requirements

### Requirement: 定位编号跨回合保留

成功的 `ocr_locate` MUST 把编号到逻辑中心的映射写入当前会话。后续用户回合在同一会话中按 `target_id` 点击时 MUST 仍能命中，直到下一次成功定位覆盖。会话 JSON 缺少该字段时 MUST 视为没有定位结果。

#### Scenario: 下一回合按编号点击

- **WHEN** 上一回合 `ocr_locate` 记下 `id=1` 的逻辑中心，新回合批准 `mouse_click` 且 `target_id` 为 `1`
- **THEN** 指针移到该逻辑中心，且 MUST NOT 报没有该编号
