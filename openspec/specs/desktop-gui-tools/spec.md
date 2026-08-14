# desktop-gui-tools Specification

## Purpose

基于 PyAutoGUI 的桌面感知与执行（截图、屏幕信息、移鼠、点按、拖拽、滚轮、输入文本、按键），含视图像素换算、权限错误与安全约束。

## Requirements

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

### Requirement: 查询屏幕与指针

`screen_info` MUST 返回主屏逻辑分辨率、`scale` 与当前鼠标逻辑坐标。MUST NOT 要求确认。

#### Scenario: 读取屏幕信息

- **WHEN** 模型调用 `screen_info`
- **THEN** 结果包含 `screen_width`、`screen_height`、`scale`、`mouse_x`、`mouse_y`

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

### Requirement: 滚轮滚动

系统 MUST 提供 `mouse_scroll`。该工具 MUST 接受整数 `clicks`（正数向上、负数向下），可选视图像素 `x`/`y`；给出坐标时 MUST 先换算为逻辑像素并移动，再滚动。MUST 要求确认，会话普通自动批准 MUST NOT 跳过。MUST NOT 提供横向滚动。

#### Scenario: 在指定点向上滚动

- **WHEN** 用户批准 `mouse_scroll`，`clicks` 为正，并给出最近一次截图视图内的 `x`、`y`
- **THEN** 指针先移到换算后的逻辑坐标，再向上滚动相应格数

#### Scenario: 拒绝滚动

- **WHEN** 模型调用 `mouse_scroll` 且用户拒绝
- **THEN** 不移动指针、不发送滚轮，工具结果为已取消

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

### Requirement: 定位编号跨回合保留

成功的 `ocr_locate` MUST 把编号到逻辑中心的映射写入当前会话。后续用户回合在同一会话中按 `target_id` 点击时 MUST 仍能命中，直到下一次成功定位覆盖。会话 JSON 缺少该字段时 MUST 视为没有定位结果。

#### Scenario: 下一回合按编号点击

- **WHEN** 上一回合 `ocr_locate` 记下 `id=1` 的逻辑中心，新回合批准 `mouse_click` 且 `target_id` 为 `1`
- **THEN** 指针移到该逻辑中心，且 MUST NOT 报没有该编号

### Requirement: 输入文本与按键分离

`keyboard_type` MUST 只接受文本并写入当前前台窗口；MUST NOT 接受按键名。含非 ASCII 的文本 MUST 通过剪贴板粘贴，不得静默丢字。`keyboard_press` MUST 只接受白名单键名或组合键；MUST NOT 接受自由文本。白名单外的键名 MUST 拒绝。关机或退出登录相关组合 MUST 拒绝。二者 MUST 要求确认，会话普通自动批准 MUST NOT 跳过。

#### Scenario: 写入 ASCII 文本

- **WHEN** 用户批准 `keyboard_type`，`text` 为 `1+1`
- **THEN** 该文本被输入到当前前台窗口

#### Scenario: 按下回车

- **WHEN** 用户批准 `keyboard_press`，`keys` 为 `enter`
- **THEN** 系统按下回车，且不把 `enter` 当作普通文本写入

#### Scenario: 拒绝未知键名

- **WHEN** 模型调用 `keyboard_press`，`keys` 含白名单外的名称
- **THEN** 工具返回错误且不发送按键

#### Scenario: 拒绝危险热键

- **WHEN** 模型调用 `keyboard_press`，`keys` 为退出登录或关机相关组合
- **THEN** 工具返回错误且不发送按键

### Requirement: 桌面调用不阻塞界面

桌面后端的同步调用 MUST 在工作线程中执行。生产实现 MUST 开启 failsafe，并在连续动作之间加入短暂暂停。测试 MUST 注入假后端，MUST NOT 在 CI 中驱动真实鼠标、键盘或屏幕。

#### Scenario: 假后端记录点击

- **WHEN** 测试用假后端调用 `mouse_click`
- **THEN** 后端记录调用参数，真实指针位置不变

### Requirement: 权限失败对用户可读

屏幕录制或辅助功能缺失时，工具 MUST 返回可照做的中文步骤（系统设置中的屏幕录制 / 辅助功能，勾选运行本程序的终端）。MUST NOT 只抛出未翻译的英文异常。

#### Scenario: 辅助功能未授权

- **WHEN** 键鼠 API 因辅助功能权限失败
- **THEN** 工具结果包含中文授权步骤，图继续进入 `think`
