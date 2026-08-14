## ADDED Requirements

### Requirement: 滚轮滚动

系统 MUST 提供 `mouse_scroll`。该工具 MUST 接受整数 `clicks`（正数向上、负数向下），可选视图像素 `x`/`y`；给出坐标时 MUST 先换算为逻辑像素并移动，再滚动。MUST 要求确认，会话普通自动批准 MUST NOT 跳过。MUST NOT 提供横向滚动。

#### Scenario: 在指定点向上滚动

- **WHEN** 用户批准 `mouse_scroll`，`clicks` 为正，并给出最近一次截图视图内的 `x`、`y`
- **THEN** 指针先移到换算后的逻辑坐标，再向上滚动相应格数

#### Scenario: 拒绝滚动

- **WHEN** 模型调用 `mouse_scroll` 且用户拒绝
- **THEN** 不移动指针、不发送滚轮，工具结果为已取消

### Requirement: 视图像素换算为逻辑像素

`mouse_move`、`mouse_click`、`mouse_drag`、`mouse_scroll` 的坐标输入 MUST 解释为最近一次成功 `screenshot` 回注给主模型的那张图上的像素。工具 MUST 按该图的视图宽高、逻辑宽高与区域原点换算成逻辑像素，再交给桌面后端。换算后越界 MUST 夹紧到主屏内并在结果中说明。尚无成功截图时，输入 MUST 当作逻辑像素，并在结果中说明未做视图换算。

#### Scenario: 按视图像素点击

- **WHEN** 最近一次全屏截图的视图宽为逻辑宽的一半，模型批准后的 `mouse_click` 给出视图坐标 `(100, 40)`
- **THEN** 后端收到的逻辑坐标为 `(200, 80)`（在未夹紧的情况下）

#### Scenario: 区域截图后的局部坐标

- **WHEN** 最近一次截图 `region` 原点为逻辑 `(200, 100)`，视图与区域逻辑尺寸之比为 1，模型给出视图 `(10, 15)`
- **THEN** 后端收到的逻辑坐标为 `(210, 115)`

#### Scenario: 按定位编号点击

- **WHEN** 最近一次 `ocr_locate` 成功且含 `id=1`，用户批准 `mouse_click` 且 `target_id` 为 `1`
- **THEN** 指针移到该项的逻辑中心并点击，不使用本次调用中的 `x`/`y`

## MODIFIED Requirements

### Requirement: 截取主屏并返回逻辑元数据

`screenshot` MUST 截取主屏（或给定逻辑像素 `region`），把 PNG 写入 `artifacts/screenshots/`，并返回文本摘要：路径、逻辑宽高、发给主模型后的视图宽高、区域逻辑原点、`scale`、当前光标坐标，以及 `coordinate_space` 为 `view`。全黑或过小的图像 MUST 视为屏幕录制权限失败，返回中文步骤，且 MUST NOT 把空图发给模型。默认 MUST 在图上标注当前光标位置。成功截图 MUST 更新后续鼠标工具使用的视图坐标系。

#### Scenario: 全屏截图成功

- **WHEN** 模型调用 `screenshot` 且屏幕录制已授权
- **THEN** 工具写入 PNG，摘要包含 `path`、逻辑宽高、`view_width`、`view_height`、`origin`、`scale`、`cursor`、`coordinate_space`，并附带该图像引用

#### Scenario: 未授权得到黑图

- **WHEN** 截图结果全黑或尺寸过小
- **THEN** 工具返回屏幕录制授权的中文步骤，且不把该图作为模型输入

### Requirement: 逻辑坐标移动指针

`mouse_move` MUST 将输入的视图像素换算为逻辑像素后移动指针。越界坐标 MUST 夹紧到主屏内，并在结果中说明。MUST NOT 要求确认。可选 `target_id` 命中最近一次 `ocr_locate` 结果时，MUST 改用该项逻辑中心。

#### Scenario: 移动到可见点

- **WHEN** 模型调用 `mouse_move`，换算后的逻辑坐标在主屏内
- **THEN** 指针移动到该逻辑坐标

#### Scenario: 越界夹紧

- **WHEN** 模型调用 `mouse_move`，换算后的 `x` 或 `y` 超出主屏
- **THEN** 指针移到夹紧后的位置，结果说明发生了夹紧

### Requirement: 点击与拖拽需确认

`mouse_click` MUST 支持左/右/中键与单击/双击；若提供坐标或 `target_id` 则先移动再点击。`mouse_drag` MUST 将 `(x1, y1)` 与 `(x2, y2)` 从视图像素换算后拖拽。二者 MUST 要求确认，会话普通自动批准 MUST NOT 跳过。

#### Scenario: 带坐标单击

- **WHEN** 用户批准 `mouse_click`，参数为视图内的 `x`、`y`
- **THEN** 指针先移到换算后的逻辑点再单击左键

#### Scenario: 拒绝拖拽

- **WHEN** 模型调用 `mouse_drag` 且用户拒绝
- **THEN** 不移动指针、不按下鼠标，工具结果为已取消
